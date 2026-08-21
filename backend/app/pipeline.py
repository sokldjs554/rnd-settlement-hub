"""집행 건 검증 파이프라인 (워커에서 실행).

제출된 집행 건 하나에 대해:
  ① AI 증빙 구조화 → ② AI 비목 제안 → ③ 외부 데이터 조회(국세청·공휴일·중복·예산)
  → ④ 룰 15종 평가 → ⑤ 결과 저장 + 상태 전이(NEEDS_REVIEW) + 담당자 알림

원칙:
- 외부 호출(AI·국세청)은 DB 행 잠금 없이 수행한다 (잠금 보유 시간 최소화)
- AI/외부 API가 실패해도 파이프라인은 멈추지 않는다 — 실패 사실이 룰 플래그로 남을 뿐
- 모든 AI 호출은 ai_runs에 기록된다 (모델·프롬프트 버전·출력·지연시간)
"""

import logging
import time
from dataclasses import asdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.base import AIClient, AIUnavailableError, CategorySuggestion, ExtractedDoc
from app.ai.null import NullAIClient, get_ai_client
from app.external.holidays import is_nonworking_day
from app.external.nts import check_vendor_status
from app.models import (
    AutomationRun,
    Budget,
    Evidence,
    Expense,
    Project,
    ValidationResult,
)
from app.models.enums import AiRunKind, AiRunStatus, ExpenseStatus
from app.rules import ExpenseSnapshot, RuleContext, run_all
from app.services import expense as expense_service
from app.services.ai_log import record_ai_run
from app.services.budget import approved_sum
from app.services.storage import evidence_absolute_path

logger = logging.getLogger(__name__)


def run_expense_pipeline(db: Session, run: AutomationRun) -> None:
    assert run.expense_id is not None
    expense = db.get(Expense, run.expense_id)
    if expense is None or expense.deleted_at is not None:
        logger.info("run %d: 집행 건이 삭제되어 파이프라인을 건너뜀", run.id)
        return

    # SUBMITTED → VALIDATING. 이미 다른 상태면 중복/뒤늦은 실행이므로 조용히 종료
    if expense.status == ExpenseStatus.SUBMITTED:
        expense.status = ExpenseStatus.VALIDATING
        db.commit()
    elif expense.status != ExpenseStatus.VALIDATING:
        logger.info("run %d: 상태 %s — 파이프라인 불필요", run.id, expense.status)
        return

    ai_client = get_ai_client()
    ai_available = not isinstance(ai_client, NullAIClient)

    extraction, extraction_failed = _extract_first_evidence(db, expense, ai_client)
    suggestion = _suggest_category(db, expense, ai_client, extraction)

    vendor_status = None
    if expense.vendor_biz_no:
        vendor_status = check_vendor_status(db, expense.vendor_biz_no)

    duplicates = _find_duplicates(db, expense)
    nonworking = is_nonworking_day(db, expense.spent_at)

    budget = db.execute(
        select(Budget).where(
            Budget.project_id == expense.project_id, Budget.category == expense.category
        )
    ).scalar_one_or_none()
    already_approved = approved_sum(db, expense.project_id, expense.category)

    project = db.get(Project, expense.project_id)
    assert project is not None  # FK 보장

    ctx = RuleContext(
        expense=ExpenseSnapshot(
            id=expense.id,
            project_id=expense.project_id,
            category=expense.category,
            title=expense.title,
            vendor_name=expense.vendor_name,
            vendor_biz_no=expense.vendor_biz_no,
            amount=expense.amount,
            spent_at=expense.spent_at,
        ),
        project_start=project.start_date,
        project_end=project.end_date,
        budget_amount=budget.amount if budget else None,
        approved_amount=already_approved,
        evidence_count=len(expense.evidences),
        ai_available=ai_available,
        extraction=extraction,
        extraction_failed=extraction_failed,
        suggestion=suggestion,
        vendor_status=vendor_status,
        duplicate_expense_ids=duplicates,
        nonworking_day=nonworking,
    )

    for result in run_all(ctx):
        db.add(
            ValidationResult(
                expense_id=expense.id,
                run_id=run.id,
                rule_code=result.rule_code,
                severity=result.severity,
                message=result.message,
                detail=result.detail,
            )
        )

    expense_service.mark_validated(db, expense.id)
    db.commit()


def _extract_first_evidence(
    db: Session, expense: Expense, ai_client: AIClient
) -> tuple[ExtractedDoc | None, bool]:
    """대표 증빙 1건(먼저 업로드된 것)을 구조화한다. MVP 제한 — 다중 증빙은 향후 개선.

    반환: (추출 결과 | None, 시도했으나 실패했는가)
    """
    evidence = db.execute(
        select(Evidence).where(Evidence.expense_id == expense.id).order_by(Evidence.id).limit(1)
    ).scalar_one_or_none()
    if evidence is None:
        return None, False

    started = time.monotonic()
    try:
        file_bytes = evidence_absolute_path(evidence.file_path).read_bytes()
        extraction = ai_client.extract_document(
            file_bytes=file_bytes, mime_type=evidence.mime_type
        )
    except AIUnavailableError:
        return None, False  # AI 미사용 모드 — R-AI-001이 ai_available=False로 플래그
    except Exception as exc:  # AI 실패가 파이프라인을 죽이면 안 된다
        logger.warning("expense %d: AI 추출 실패: %s", expense.id, exc)
        record_ai_run(
            db,
            expense_id=expense.id,
            evidence_id=evidence.id,
            kind=AiRunKind.DOC_EXTRACTION,
            client=ai_client,
            status=AiRunStatus.FAILED,
            error=str(exc)[:2000],
            latency_ms=int((time.monotonic() - started) * 1000),
        )
        return None, True

    record_ai_run(
        db,
        expense_id=expense.id,
        evidence_id=evidence.id,
        kind=AiRunKind.DOC_EXTRACTION,
        client=ai_client,
        status=AiRunStatus.SUCCESS,
        output_json=_extraction_to_json(extraction),
        confidence=extraction.confidence,
        latency_ms=int((time.monotonic() - started) * 1000),
    )
    return extraction, False


def _suggest_category(
    db: Session,
    expense: Expense,
    ai_client: AIClient,
    extraction: ExtractedDoc | None,
) -> CategorySuggestion | None:
    started = time.monotonic()
    try:
        suggestion = ai_client.suggest_category(
            extraction=extraction,
            title=expense.title,
            vendor_name=expense.vendor_name,
            amount=int(expense.amount),
            purpose=expense.purpose,
        )
    except AIUnavailableError:
        return None
    except Exception as exc:
        logger.warning("expense %d: AI 비목 제안 실패: %s", expense.id, exc)
        record_ai_run(
            db,
            expense_id=expense.id,
            kind=AiRunKind.CATEGORY_SUGGESTION,
            client=ai_client,
            status=AiRunStatus.FAILED,
            error=str(exc)[:2000],
            latency_ms=int((time.monotonic() - started) * 1000),
        )
        return None

    record_ai_run(
        db,
        expense_id=expense.id,
        kind=AiRunKind.CATEGORY_SUGGESTION,
        client=ai_client,
        status=AiRunStatus.SUCCESS,
        output_json={"rationale": suggestion.rationale},
        suggested_category=suggestion.category,
        confidence=suggestion.confidence,
        latency_ms=int((time.monotonic() - started) * 1000),
    )
    return suggestion


def _extraction_to_json(extraction: ExtractedDoc) -> dict:
    data = asdict(extraction)
    if extraction.issued_at is not None:
        data["issued_at"] = extraction.issued_at.isoformat()
    if extraction.confidence is not None:
        data["confidence"] = float(extraction.confidence)
    return data


def _find_duplicates(db: Session, expense: Expense) -> list[int]:
    """같은 과제·거래처·금액·일자의 다른 건 (반려·삭제 건 제외)."""
    if not expense.vendor_biz_no:
        return []
    rows = db.execute(
        select(Expense.id).where(
            Expense.id != expense.id,
            Expense.project_id == expense.project_id,
            Expense.vendor_biz_no == expense.vendor_biz_no,
            Expense.amount == expense.amount,
            Expense.spent_at == expense.spent_at,
            Expense.deleted_at.is_(None),
            Expense.status != ExpenseStatus.REJECTED,
        )
    )
    return [row[0] for row in rows]
