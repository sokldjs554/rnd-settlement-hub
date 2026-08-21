"""백그라운드 워커 프로세스.

실행:  python -m app.worker
API 서버와 같은 코드베이스, 다른 프로세스. 여러 개 띄워도 안전하다
(작업 선점이 FOR UPDATE SKIP LOCKED이므로 같은 작업이 중복 실행되지 않는다).

장애 시나리오별 동작:
- 작업 처리 중 예외 → 재큐잉(최대 3회), 최종 실패 시 FAILED + 담당자 알림
  + 집행 건을 NEEDS_REVIEW로 전환해 워크플로가 막히지 않게 한다(수기 검토 플래그 포함)
- 워커 프로세스 사망 → RUNNING 고아 작업을 다음 워커가 requeue_stale로 회수
"""

import logging
import time

from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import AutomationRun, Expense, ValidationResult
from app.models.enums import (
    AutomationKind,
    AutomationStatus,
    ExpenseStatus,
    ValidationSeverity,
)
from app.pipeline import run_expense_pipeline
from app.services import queue
from app.services.notification import notify_managers

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 2.0
STALE_CHECK_EVERY_LOOPS = 15  # 약 30초마다 고아 작업 회수


def execute(db: Session, run: AutomationRun) -> None:
    try:
        if run.kind == AutomationKind.EXPENSE_PIPELINE:
            run_expense_pipeline(db, run)
        elif run.kind == AutomationKind.REPORT_GENERATION:
            # 보고서 서술 초안 생성 — report 서비스에서 구현
            from app.services.report import run_report_generation

            run_report_generation(db, run)
        queue.finish(db, run)
    except Exception as exc:
        logger.exception("run %d 실패 (attempt %d)", run.id, run.attempt)
        db.rollback()
        queue.finish(db, run, error=f"{type(exc).__name__}: {exc}"[:2000])
        if run.status == AutomationStatus.FAILED:
            _handle_permanent_failure(db, run)


def _handle_permanent_failure(db: Session, run: AutomationRun) -> None:
    """재시도가 소진된 작업: 워크플로를 막지 않도록 사람에게 넘긴다."""
    if run.kind == AutomationKind.EXPENSE_PIPELINE and run.expense_id is not None:
        expense = db.get(Expense, run.expense_id)
        if expense is not None and expense.status in (
            ExpenseStatus.SUBMITTED,
            ExpenseStatus.VALIDATING,
        ):
            expense.status = ExpenseStatus.NEEDS_REVIEW
            db.add(
                ValidationResult(
                    expense_id=expense.id,
                    run_id=run.id,
                    rule_code="R-SYS-001",
                    severity=ValidationSeverity.WARN,
                    message="자동 검증 파이프라인이 실패했습니다. 수기 검토가 필요합니다.",
                    detail={"error": run.error},
                )
            )
    notify_managers(
        db,
        "automation_failed",
        {"run_id": run.id, "kind": run.kind.value, "error": run.error},
    )
    db.commit()


def main_loop() -> None:
    logger.info("워커 시작 (poll=%.1fs)", POLL_INTERVAL_SECONDS)
    loops = 0
    while True:
        loops += 1
        db = SessionLocal()
        try:
            if loops % STALE_CHECK_EVERY_LOOPS == 1:
                recovered = queue.requeue_stale(db)
                if recovered:
                    logger.warning("고아 작업 %d건 회수", recovered)
            run = queue.claim_next(db)
            if run is None:
                time.sleep(POLL_INTERVAL_SECONDS)
                continue
            logger.info("run %d 처리 시작 (%s, attempt %d)", run.id, run.kind, run.attempt)
            execute(db, run)
        finally:
            db.close()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    main_loop()
