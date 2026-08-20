from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin
from app.models.enums import ReportStatus


class Report(TimestampMixin, Base):
    """월별 정산보고서.

    summary_json: SQL 집계 결과 스냅샷(비목별 예산/집행/잔액 등) — 숫자는 AI가 만들지 않는다.
    narrative_md: 서술부. AI 초안(ai_runs에 기록)을 담당자가 수정해 확정한 최종본.
    FINAL 확정 시 포함된 집행 건들의 report_id가 설정되고 잠긴다.
    """

    __tablename__ = "reports"
    __table_args__ = (
        UniqueConstraint("project_id", "period_year", "period_month", name="uq_reports_period"),
        CheckConstraint("period_month BETWEEN 1 AND 12", name="ck_reports_month_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    period_year: Mapped[int] = mapped_column(Integer, nullable=False)
    period_month: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[ReportStatus] = mapped_column(
        Enum(ReportStatus, name="report_status"), nullable=False, default=ReportStatus.DRAFT
    )
    summary_json: Mapped[dict | None] = mapped_column(JSONB)
    narrative_md: Mapped[str | None] = mapped_column(Text)
    generated_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
