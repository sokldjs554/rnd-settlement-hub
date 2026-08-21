from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin
from app.models.enums import AutomationKind, AutomationStatus


class AutomationRun(TimestampMixin, Base):
    """자동화 파이프라인 실행 기록이자 DB 기반 작업 큐.

    별도 브로커(Redis/Celery) 없이 이 테이블이 큐 역할을 한다:
    - 등록: idempotency_key UNIQUE로 같은 작업의 중복 등록을 DB 레벨에서 차단
    - 선점: 워커가 QUEUED 행을 SELECT ... FOR UPDATE SKIP LOCKED로 가져간다
    - 장애 복구: RUNNING인 채 started_at이 임계를 넘긴 행(워커 사망)은 재큐잉,
      attempt가 한도를 넘으면 FAILED 처리 후 담당자 알림
    """

    __tablename__ = "automation_runs"
    __table_args__ = (
        # 대상은 집행 건 또는 보고서 중 정확히 하나
        CheckConstraint(
            "(expense_id IS NOT NULL)::int + (report_id IS NOT NULL)::int = 1",
            name="ck_automation_runs_single_target",
        ),
        Index("ix_automation_runs_status_id", "status", "id"),  # 워커 폴링용
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[AutomationKind] = mapped_column(
        Enum(AutomationKind, name="automation_kind"), nullable=False
    )
    expense_id: Mapped[int | None] = mapped_column(ForeignKey("expenses.id", ondelete="CASCADE"))
    report_id: Mapped[int | None] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"))
    status: Mapped[AutomationStatus] = mapped_column(
        Enum(AutomationStatus, name="automation_status"),
        nullable=False,
        default=AutomationStatus.QUEUED,
    )
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    idempotency_key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
