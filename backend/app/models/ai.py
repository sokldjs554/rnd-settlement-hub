from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.enums import AiRunKind, AiRunStatus, BudgetCategory


class AiRun(Base):
    """모든 AI 호출 기록.

    핵심 원칙: AI의 제안/출력은 이 테이블에만 저장하고, 인간이 확정한 값
    (expenses.category, reports.narrative_md 최종본)과 구조적으로 분리한다.
    프롬프트는 코드 저장소에서 버전 관리하고 prompt_version으로 어떤 버전이
    이 결과를 만들었는지 추적한다.
    """

    __tablename__ = "ai_runs"
    __table_args__ = (
        # 집행 건 대상(추출/비목 제안) 또는 보고서 대상(서술 초안) 중 하나에 속해야 한다
        CheckConstraint(
            "(expense_id IS NOT NULL) OR (report_id IS NOT NULL)",
            name="ck_ai_runs_has_target",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_ai_runs_confidence_range",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    expense_id: Mapped[int | None] = mapped_column(
        ForeignKey("expenses.id", ondelete="CASCADE"), index=True
    )
    report_id: Mapped[int | None] = mapped_column(
        ForeignKey("reports.id", ondelete="CASCADE"), index=True
    )
    evidence_id: Mapped[int | None] = mapped_column(ForeignKey("evidences.id", ondelete="SET NULL"))
    kind: Mapped[AiRunKind] = mapped_column(Enum(AiRunKind, name="ai_run_kind"), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[AiRunStatus] = mapped_column(
        Enum(AiRunStatus, name="ai_run_status"), nullable=False
    )
    output_json: Mapped[dict | None] = mapped_column(JSONB)  # structured output 원문
    suggested_category: Mapped[BudgetCategory | None] = mapped_column(
        Enum(BudgetCategory, name="budget_category")
    )
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))  # 0.000 ~ 1.000
    error: Mapped[str | None] = mapped_column(Text)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
