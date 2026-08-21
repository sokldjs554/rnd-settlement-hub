"""예산 조회·잔액 계산.

잔액을 컬럼으로 비정규화하지 않고 '승인된 집행의 SUM'으로 계산한다.
정합성이 우선이고, ix_expenses_project_category_status 인덱스로 조회 비용을 낮춘다.
"""

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Budget, Expense
from app.models.enums import BudgetCategory, ExpenseStatus
from app.schemas.project import BudgetSummary


def approved_sum(
    db: Session, project_id: int, category: BudgetCategory, *, exclude_expense_id: int | None = None
) -> Decimal:
    """해당 과제×비목에서 승인된 집행 총액."""
    stmt = select(func.coalesce(func.sum(Expense.amount), 0)).where(
        Expense.project_id == project_id,
        Expense.category == category,
        Expense.status == ExpenseStatus.APPROVED,
        Expense.deleted_at.is_(None),
    )
    if exclude_expense_id is not None:
        stmt = stmt.where(Expense.id != exclude_expense_id)
    return Decimal(db.execute(stmt).scalar_one())


def get_budget_for_update(
    db: Session, project_id: int, category: BudgetCategory
) -> Budget | None:
    """승인 트랜잭션용: 예산 행에 행 잠금(FOR UPDATE)을 건다.

    동시 승인 요청이 같은 비목 예산을 놓고 경쟁할 때, 잠금을 잡은 쪽이 잔액을 확정한 뒤
    커밋할 때까지 다른 쪽이 대기하게 만들어 예산 초과 승인을 막는다.
    """
    return db.execute(
        select(Budget)
        .where(Budget.project_id == project_id, Budget.category == category)
        .with_for_update()
    ).scalar_one_or_none()


def budget_summaries(db: Session, project_id: int) -> list[BudgetSummary]:
    """과제의 비목별 예산/승인 집행/잔액 목록 (프로젝트 상세·대시보드용)."""
    budgets = (
        db.execute(select(Budget).where(Budget.project_id == project_id).order_by(Budget.id))
        .scalars()
        .all()
    )
    # 비목별 승인 합계를 한 번의 GROUP BY로 조회
    rows = db.execute(
        select(Expense.category, func.coalesce(func.sum(Expense.amount), 0))
        .where(
            Expense.project_id == project_id,
            Expense.status == ExpenseStatus.APPROVED,
            Expense.deleted_at.is_(None),
        )
        .group_by(Expense.category)
    ).all()
    sums: dict[BudgetCategory, Decimal] = {category: total for category, total in rows}
    return [
        BudgetSummary(
            category=b.category,
            budget=b.amount,
            approved=(approved := sums.get(b.category, Decimal(0))),
            remaining=b.amount - approved,
        )
        for b in budgets
    ]
