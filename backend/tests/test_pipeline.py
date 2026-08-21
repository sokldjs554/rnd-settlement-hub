"""파이프라인 통합 테스트: 제출 → 큐 선점 → 검증 실행 → NEEDS_REVIEW 전이.

실 DB(큐 포함)를 쓰고 AI만 Fake로 대체한다.
"""

from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

import app.pipeline as pipeline_module
from app.config import get_settings
from app.models import AiRun, Evidence, Expense, Notification, ValidationResult
from app.models.enums import (
    AiRunKind,
    AutomationStatus,
    ExpenseStatus,
    UserRole,
    ValidationSeverity,
)
from app.pipeline import run_expense_pipeline
from app.services import expense as expense_service
from app.services import queue
from app.worker import execute
from tests.factories import make_budget, make_expense, make_project, make_user
from tests.fakes import FakeAIClient

VALID_BIZ_NO = "1234567891"


def _prepare_submitted_expense(db: Session, *, with_evidence: bool = True) -> Expense:
    project = make_project(db)
    make_budget(db, project, amount=10_000_000)
    researcher = make_user(db, email="r@corp.kr")
    make_user(db, email="m@corp.kr", role=UserRole.MANAGER)
    expense = make_expense(db, project, researcher)
    expense.vendor_biz_no = VALID_BIZ_NO
    if with_evidence:
        file_path = Path(get_settings().upload_dir) / f"{expense.id}" / "test.pdf"
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(b"%PDF-1.4 fake")
        db.add(
            Evidence(
                expense_id=expense.id,
                file_path=f"{expense.id}/test.pdf",
                file_name="test.pdf",
                mime_type="application/pdf",
                size_bytes=13,
                uploaded_by=researcher.id,
            )
        )
    db.commit()
    return expense_service.submit(db, expense.id, researcher)


def test_pipeline_happy_path(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeAIClient()
    # Fake 추출값을 실제 집행 건과 일치시킨다 (전부 PASS가 나와야 하는 시나리오)
    fake.extraction = replace(
        fake.extraction, biz_no=VALID_BIZ_NO, total_amount=500_000, issued_at=date(2026, 3, 10)
    )
    monkeypatch.setattr(pipeline_module, "get_ai_client", lambda: fake)

    expense = _prepare_submitted_expense(db)
    run = queue.claim_next(db)
    assert run is not None and run.expense_id == expense.id

    run_expense_pipeline(db, run)
    queue.finish(db, run)

    db.expire_all()
    refreshed = db.get(Expense, expense.id)
    assert refreshed is not None and refreshed.status == ExpenseStatus.NEEDS_REVIEW
    assert run.status == AutomationStatus.SUCCEEDED

    results = db.execute(
        select(ValidationResult).where(ValidationResult.run_id == run.id)
    ).scalars().all()
    by_code = {r.rule_code: r for r in results}
    assert by_code["R-EVD-002"].severity == ValidationSeverity.PASS
    assert by_code["R-VND-003"].severity == ValidationSeverity.WARN  # 국세청 키 없음 → 미확인

    # AI 호출이 전부 기록되었다
    ai_runs = db.execute(select(AiRun).where(AiRun.expense_id == expense.id)).scalars().all()
    kinds = {r.kind for r in ai_runs}
    assert kinds == {AiRunKind.DOC_EXTRACTION, AiRunKind.CATEGORY_SUGGESTION}
    assert all(r.model == "fake-model" and r.prompt_version == "test-v1" for r in ai_runs)

    # 담당자 알림 발송
    notes = db.execute(select(Notification)).scalars().all()
    assert any(n.type == "expense_needs_review" for n in notes)


def test_pipeline_degraded_mode_without_ai(db: Session) -> None:
    """AI 키가 없어도 파이프라인은 완주하고, 수기 대조 플래그(R-AI-001)가 남는다."""
    expense = _prepare_submitted_expense(db)
    run = queue.claim_next(db)
    assert run is not None

    run_expense_pipeline(db, run)  # 기본 get_ai_client → NullAIClient (테스트 env에 키 없음)

    results = db.execute(
        select(ValidationResult).where(ValidationResult.run_id == run.id)
    ).scalars().all()
    by_code = {r.rule_code: r for r in results}
    assert by_code["R-AI-001"].severity == ValidationSeverity.WARN
    assert "R-EVD-002" not in by_code  # 추출이 없으니 대사 룰은 평가되지 않는다

    db.expire_all()
    refreshed = db.get(Expense, expense.id)
    assert refreshed is not None and refreshed.status == ExpenseStatus.NEEDS_REVIEW


def test_pipeline_extraction_failure_flags_manual_review(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeAIClient(fail_extraction=True)
    monkeypatch.setattr(pipeline_module, "get_ai_client", lambda: fake)

    _prepare_submitted_expense(db)
    run = queue.claim_next(db)
    assert run is not None
    run_expense_pipeline(db, run)

    by_code = {
        r.rule_code: r
        for r in db.execute(
            select(ValidationResult).where(ValidationResult.run_id == run.id)
        ).scalars()
    }
    assert by_code["R-AI-001"].severity == ValidationSeverity.WARN

    failed_ai = db.execute(
        select(AiRun).where(AiRun.kind == AiRunKind.DOC_EXTRACTION)
    ).scalar_one()
    assert failed_ai.error is not None


def test_worker_retries_then_marks_failed_and_unblocks(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """파이프라인이 계속 죽으면 3회 재시도 후 FAILED, 집행 건은 NEEDS_REVIEW로 넘어간다."""

    def boom(db_: Session, run_) -> None:
        raise RuntimeError("의도된 파이프라인 장애")

    monkeypatch.setattr(pipeline_module, "run_expense_pipeline", boom)
    import app.worker as worker_module

    monkeypatch.setattr(worker_module, "run_expense_pipeline", boom)

    expense = _prepare_submitted_expense(db)

    for attempt in range(1, queue.MAX_ATTEMPTS + 1):
        run = queue.claim_next(db)
        assert run is not None, f"attempt {attempt}에서 작업이 큐에 없음"
        execute(db, run)

    assert run.status == AutomationStatus.FAILED
    assert queue.claim_next(db) is None  # 더 이상 재시도하지 않는다

    db.expire_all()
    refreshed = db.get(Expense, expense.id)
    assert refreshed is not None and refreshed.status == ExpenseStatus.NEEDS_REVIEW
    sys_flag = db.execute(
        select(ValidationResult).where(ValidationResult.rule_code == "R-SYS-001")
    ).scalar_one()
    assert sys_flag.severity == ValidationSeverity.WARN

    notes = db.execute(select(Notification)).scalars().all()
    assert any(n.type == "automation_failed" for n in notes)
