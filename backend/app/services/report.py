"""월별 정산보고서: SQL 집계 + AI 서술 초안 + 확정(잠금).

역할 분리(hallucination 통제의 핵심):
- 숫자: 이 모듈의 SQL 집계가 유일한 출처. summary_json에 스냅샷으로 저장된다.
- 서술: AI가 summary_json을 읽고 '초안'만 작성. 담당자가 수정해 확정한다.
"""

import logging
import time
from datetime import UTC, date, datetime
from typing import cast

from sqlalchemy import CursorResult, func, select, update
from sqlalchemy.orm import Session

from app.ai.base import AIUnavailableError
from app.ai.null import get_ai_client
from app.api.errors import AppError, not_found
from app.models import (
    Approval,
    AutomationRun,
    Budget,
    Expense,
    Project,
    Report,
    User,
)
from app.models.enums import (
    BUDGET_CATEGORY_LABELS,
    AiRunKind,
    AiRunStatus,
    ApprovalAction,
    BudgetCategory,
    ExpenseStatus,
    ReportStatus,
)
from app.services import audit, queue
from app.services.ai_log import record_ai_run
from app.services.notification import notify

logger = logging.getLogger(__name__)


def _month_range(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return start, end


def build_summary(db: Session, project_id: int, year: int, month: int) -> dict:
    """비목별 예산·집행 집계. 100% SQL — 여기 숫자가 보고서의 유일한 출처다."""
    start, end = _month_range(year, month)

    budgets = (
        db.execute(select(Budget).where(Budget.project_id == project_id).order_by(Budget.id))
        .scalars()
        .all()
    )

    def approved_sums(until: date | None, since: date | None) -> dict[BudgetCategory, int]:
        stmt = (
            select(Expense.category, func.coalesce(func.sum(Expense.amount), 0))
            .where(
                Expense.project_id == project_id,
                Expense.status == ExpenseStatus.APPROVED,
                Expense.deleted_at.is_(None),
            )
            .group_by(Expense.category)
        )
        if since is not None:
            stmt = stmt.where(Expense.spent_at >= since)
        if until is not None:
            stmt = stmt.where(Expense.spent_at < until)
        return {category: int(total) for category, total in db.execute(stmt)}

    month_sums = approved_sums(until=end, since=start)
    cumulative_sums = approved_sums(until=end, since=None)

    categories = []
    for b in budgets:
        cumulative = cumulative_sums.get(b.category, 0)
        categories.append(
            {
                "category": b.category.value,
                "label": BUDGET_CATEGORY_LABELS[b.category],
                "budget": int(b.amount),
                "month_approved": month_sums.get(b.category, 0),
                "cumulative_approved": cumulative,
                "remaining": int(b.amount) - cumulative,
            }
        )

    def count_where(*conditions) -> int:
        return db.execute(
            select(func.count())
            .select_from(Expense)
            .where(
                Expense.project_id == project_id, Expense.deleted_at.is_(None), *conditions
            )
        ).scalar_one()

    month_override_count = db.execute(
        select(func.count())
        .select_from(Approval)
        .join(Expense, Approval.expense_id == Expense.id)
        .where(
            Expense.project_id == project_id,
            Approval.action == ApprovalAction.APPROVE,
            Approval.override.is_(True),
            Approval.created_at >= datetime(year, month, 1, tzinfo=UTC),
            Approval.created_at < datetime(end.year, end.month, 1, tzinfo=UTC),
        )
    ).scalar_one()

    return {
        "period": {"year": year, "month": month},
        "categories": categories,
        "totals": {
            "budget": sum(c["budget"] for c in categories),
            "month_approved": sum(c["month_approved"] for c in categories),
            "cumulative_approved": sum(c["cumulative_approved"] for c in categories),
            "remaining": sum(c["remaining"] for c in categories),
        },
        "counts": {
            "month_approved_count": count_where(
                Expense.status == ExpenseStatus.APPROVED,
                Expense.spent_at >= start,
                Expense.spent_at < end,
            ),
            "month_rejected_count": count_where(
                Expense.status == ExpenseStatus.REJECTED,
                Expense.spent_at >= start,
                Expense.spent_at < end,
            ),
            "pending_review_count": count_where(Expense.status == ExpenseStatus.NEEDS_REVIEW),
            "month_override_count": month_override_count,
        },
    }


def create_report(db: Session, project_id: int, year: int, month: int, actor: User) -> Report:
    """보고서 생성: 집계는 즉시(SQL), 서술 초안은 큐에 등록해 비동기로 생성한다."""
    project = db.get(Project, project_id)
    if project is None:
        raise not_found("과제", project_id)
    duplicate = db.execute(
        select(Report).where(
            Report.project_id == project_id,
            Report.period_year == year,
            Report.period_month == month,
        )
    ).scalar_one_or_none()
    if duplicate is not None:
        raise AppError(
            409, "DUPLICATE", "해당 월의 보고서가 이미 있습니다.", {"report_id": duplicate.id}
        )

    report = Report(
        project_id=project_id,
        period_year=year,
        period_month=month,
        summary_json=build_summary(db, project_id, year, month),
        generated_by=actor.id,
    )
    db.add(report)
    db.flush()
    queue.enqueue_report_generation(db, report.id)
    audit.log(
        db,
        actor_id=actor.id,
        entity_type="report",
        entity_id=report.id,
        action="create",
        after={"period": f"{year}-{month:02d}"},
    )
    db.commit()
    return report


def finalize(db: Session, report_id: int, actor: User) -> Report:
    """확정: 숫자 스냅샷을 다시 집계해 고정하고, 기간 내 승인 건들을 이 보고서에 묶어 잠근다."""
    report = db.execute(
        select(Report).where(Report.id == report_id).with_for_update()
    ).scalar_one_or_none()
    if report is None:
        raise not_found("보고서", report_id)
    if report.status != ReportStatus.DRAFT:
        raise AppError(409, "INVALID_STATE_TRANSITION", "이미 확정된 보고서입니다.")

    start, end = _month_range(report.period_year, report.period_month)
    # 확정 시점 기준으로 숫자를 다시 집계해 스냅샷을 고정한다
    report.summary_json = build_summary(
        db, report.project_id, report.period_year, report.period_month
    )
    # UPDATE의 반환은 CursorResult(rowcount 제공) — Session.execute의 타입이 넓어 cast한다
    locked = cast(
        CursorResult,
        db.execute(
            update(Expense)
            .where(
                Expense.project_id == report.project_id,
                Expense.status == ExpenseStatus.APPROVED,
                Expense.deleted_at.is_(None),
                Expense.spent_at >= start,
                Expense.spent_at < end,
                Expense.report_id.is_(None),
            )
            .values(report_id=report.id)
        ),
    )
    report.status = ReportStatus.FINAL
    report.finalized_at = datetime.now(UTC)
    audit.log(
        db,
        actor_id=actor.id,
        entity_type="report",
        entity_id=report.id,
        action="finalize",
        after={"locked_expenses": locked.rowcount},
    )
    db.commit()
    return report


def run_report_generation(db: Session, run: AutomationRun) -> None:
    """워커 전용: AI 서술 초안 생성. 실패해도 보고서(집계)는 이미 완성돼 있다."""
    assert run.report_id is not None
    report = db.get(Report, run.report_id)
    if report is None or report.status != ReportStatus.DRAFT:
        return

    ai_client = get_ai_client()
    started = time.monotonic()
    try:
        draft = ai_client.draft_report_narrative(summary=report.summary_json or {})
    except AIUnavailableError:
        notify(
            db,
            report.generated_by,
            "report_generated",
            {"report_id": report.id, "ai_narrative": False},
        )
        db.commit()
        return
    # 그 외 예외는 워커의 재시도 정책에 맡긴다 (전파)

    record_ai_run(
        db,
        report_id=report.id,
        kind=AiRunKind.REPORT_NARRATIVE,
        client=ai_client,
        status=AiRunStatus.SUCCESS,
        output_json={"narrative_md": draft},
        latency_ms=int((time.monotonic() - started) * 1000),
    )
    # 담당자가 이미 서술을 쓰기 시작했다면 덮어쓰지 않는다 (인간 판단 우선)
    if report.narrative_md is None:
        report.narrative_md = draft
    notify(
        db,
        report.generated_by,
        "report_generated",
        {"report_id": report.id, "ai_narrative": True},
    )
    db.commit()
