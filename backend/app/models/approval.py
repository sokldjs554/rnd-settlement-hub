from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Text, false, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.enums import ApprovalAction


class Approval(Base):
    """인간의 승인/반려 판단 이력. AI 판단(ai_runs)과 분리된 불변 기록.

    override=True는 FAIL 룰이 있는 건을 담당자가 사유를 들어 승인한 경우다.
    현실 업무에는 예외가 있으므로 차단 대신 기록을 남기는 설계를 택했다.
    """

    __tablename__ = "approvals"

    id: Mapped[int] = mapped_column(primary_key=True)
    expense_id: Mapped[int] = mapped_column(
        ForeignKey("expenses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    action: Mapped[ApprovalAction] = mapped_column(
        Enum(ApprovalAction, name="approval_action"), nullable=False
    )
    override: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=false())
    comment: Mapped[str | None] = mapped_column(Text)  # 반려·override 시 서비스 레이어에서 필수
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
