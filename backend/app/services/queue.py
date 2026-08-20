"""DB 기반 작업 큐 (automation_runs 테이블).

Celery/Redis 대신 PostgreSQL로 큐를 구현한 이유:
- 이 규모(사내 수십 명, 초당 수 건)에서 브로커는 과잉 인프라다
- 작업 등록이 업무 트랜잭션과 같은 DB에서 원자적으로 일어난다
  (집행 건 상태 변경과 큐 등록이 함께 커밋되거나 함께 롤백)
- FOR UPDATE SKIP LOCKED로 워커 다중 실행에도 안전한 선점이 가능하다
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AutomationRun
from app.models.enums import AutomationKind, AutomationStatus

MAX_ATTEMPTS = 3
STALE_RUNNING_MINUTES = 10  # 이 시간을 넘긴 RUNNING은 워커 사망으로 간주


def enqueue_expense_pipeline(db: Session, expense_id: int) -> AutomationRun:
    """집행 건 검증 파이프라인 작업을 등록한다 (호출자 트랜잭션에 참여, commit 없음).

    idempotency_key = expense:{id}:pipeline:{seq}. seq는 해당 건의 기존 실행 수 + 1.
    호출 전 집행 건 행을 잠근(FOR UPDATE) 상태여야 동시 제출 race에서 seq가 안전하다.
    잠금 없이 동시 등록되면 UNIQUE 제약이 최후 방어선으로 중복을 막는다.
    """
    seq = db.execute(
        select(func.count())
        .select_from(AutomationRun)
        .where(AutomationRun.expense_id == expense_id)
    ).scalar_one()
    run = AutomationRun(
        kind=AutomationKind.EXPENSE_PIPELINE,
        expense_id=expense_id,
        idempotency_key=f"expense:{expense_id}:pipeline:{seq + 1}",
    )
    db.add(run)
    db.flush()
    return run


def enqueue_report_generation(db: Session, report_id: int) -> AutomationRun:
    """보고서 서술 초안 생성 작업을 등록한다. 보고서당 1회(UNIQUE가 중복 차단)."""
    run = AutomationRun(
        kind=AutomationKind.REPORT_GENERATION,
        report_id=report_id,
        idempotency_key=f"report:{report_id}:generate",
    )
    db.add(run)
    db.flush()
    return run


def claim_next(db: Session) -> AutomationRun | None:
    """QUEUED 작업 하나를 선점한다.

    SKIP LOCKED: 다른 워커가 잡은 행은 대기 없이 건너뛰므로 워커를 여러 개 띄워도
    같은 작업이 두 번 실행되지 않는다. 선점 즉시 RUNNING으로 커밋해 소유를 확정한다.
    """
    run = db.execute(
        select(AutomationRun)
        .where(AutomationRun.status == AutomationStatus.QUEUED)
        .order_by(AutomationRun.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    ).scalar_one_or_none()
    if run is None:
        return None
    run.status = AutomationStatus.RUNNING
    run.attempt += 1
    run.started_at = datetime.now(UTC)
    db.commit()
    return run


def finish(db: Session, run: AutomationRun, *, error: str | None = None) -> None:
    """작업 종료 처리. 실패 시 남은 시도가 있으면 재큐잉한다 (commit 포함)."""
    run.finished_at = datetime.now(UTC)
    if error is None:
        run.status = AutomationStatus.SUCCEEDED
    elif run.attempt >= MAX_ATTEMPTS:
        run.status = AutomationStatus.FAILED
        run.error = error
    else:
        run.status = AutomationStatus.QUEUED  # 재시도
        run.error = error
        run.started_at = None
        run.finished_at = None
    db.commit()


def requeue_stale(db: Session) -> int:
    """워커가 죽어 RUNNING인 채 방치된 작업을 회수한다 (워커 루프가 주기적으로 호출).

    반환값: 회수(재큐잉 또는 FAILED 처리)된 작업 수.
    """
    threshold = datetime.now(UTC) - timedelta(minutes=STALE_RUNNING_MINUTES)
    stale_runs = (
        db.execute(
            select(AutomationRun)
            .where(
                AutomationRun.status == AutomationStatus.RUNNING,
                AutomationRun.started_at < threshold,
            )
            .with_for_update(skip_locked=True)
        )
        .scalars()
        .all()
    )
    for run in stale_runs:
        if run.attempt >= MAX_ATTEMPTS:
            run.status = AutomationStatus.FAILED
            run.error = "워커 응답 없음(타임아웃)으로 실패 처리"
            run.finished_at = datetime.now(UTC)
        else:
            run.status = AutomationStatus.QUEUED
            run.started_at = None
    db.commit()
    return len(stale_runs)
