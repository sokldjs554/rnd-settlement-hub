from datetime import date
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    Enum,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import BudgetCategory, ProjectStatus


class Project(TimestampMixin, Base):
    """국가 R&D 과제."""

    __tablename__ = "projects"
    __table_args__ = (CheckConstraint("start_date <= end_date", name="ck_projects_period"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)  # 과제번호
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    agency: Mapped[str] = mapped_column(String(255), nullable=False)  # 전문기관
    start_date: Mapped[date] = mapped_column(Date, nullable=False)  # 연구기간 시작
    end_date: Mapped[date] = mapped_column(Date, nullable=False)  # 연구기간 종료
    status: Mapped[ProjectStatus] = mapped_column(
        Enum(ProjectStatus, name="project_status"), nullable=False, default=ProjectStatus.ACTIVE
    )

    budgets: Mapped[list["Budget"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class Budget(TimestampMixin, Base):
    """과제×비목 예산. 잔액은 컬럼으로 두지 않고 승인된 집행 합(SUM)으로 계산한다."""

    __tablename__ = "budgets"
    __table_args__ = (
        UniqueConstraint("project_id", "category", name="uq_budgets_project_category"),
        CheckConstraint("amount >= 0", name="ck_budgets_amount_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    category: Mapped[BudgetCategory] = mapped_column(
        Enum(BudgetCategory, name="budget_category"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 0), nullable=False)  # 원화 정수

    project: Mapped[Project] = relationship(back_populates="budgets")
