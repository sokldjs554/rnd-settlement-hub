from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import BudgetCategory, ExpenseStatus


class Expense(TimestampMixin, Base):
    """집행 건 — 이 시스템의 중심 엔티티.

    category는 항상 사람이 확정한 비목이다. AI의 제안은 ai_runs에만 저장된다.
    status 전이는 서비스 레이어에서만 수행한다(enums.ExpenseStatus 참고).
    """

    __tablename__ = "expenses"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_expenses_amount_positive"),
        Index("ix_expenses_project_status", "project_id", "status"),
        # 예산 잔액 계산(project×category×APPROVED SUM)용 인덱스
        Index("ix_expenses_project_category_status", "project_id", "category", "status"),
        Index("ix_expenses_spent_at", "spent_at"),
        Index("ix_expenses_created_by", "created_by"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    category: Mapped[BudgetCategory] = mapped_column(
        Enum(BudgetCategory, name="budget_category"), nullable=False
    )
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    vendor_name: Mapped[str] = mapped_column(String(255), nullable=False)
    vendor_biz_no: Mapped[str | None] = mapped_column(String(10))  # 사업자등록번호(숫자 10자리)
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 0), nullable=False)  # 원화 정수
    spent_at: Mapped[date] = mapped_column(Date, nullable=False)  # 집행일
    status: Mapped[ExpenseStatus] = mapped_column(
        Enum(ExpenseStatus, name="expense_status"), nullable=False, default=ExpenseStatus.DRAFT
    )
    reject_reason: Mapped[str | None] = mapped_column(Text)
    # 확정된 정산보고서에 포함되면 설정되고, 이후 수정·반려가 잠긴다
    report_id: Mapped[int | None] = mapped_column(ForeignKey("reports.id", ondelete="SET NULL"))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # soft delete

    evidences: Mapped[list["Evidence"]] = relationship(
        back_populates="expense", cascade="all, delete-orphan"
    )


class Evidence(Base):
    """증빙 파일 메타데이터. 파일 실체는 UPLOAD_DIR 볼륨(경로 추상화로 이후 S3 교체 가능)."""

    __tablename__ = "evidences"

    id: Mapped[int] = mapped_column(primary_key=True)
    expense_id: Mapped[int] = mapped_column(
        ForeignKey("expenses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)  # 업로드 원본 이름
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    expense: Mapped[Expense] = relationship(back_populates="evidences")
