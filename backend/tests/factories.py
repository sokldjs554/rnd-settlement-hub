"""테스트용 최소 엔티티 생성 헬퍼. (외부 라이브러리 없이 단순 함수로 유지)"""

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import Budget, Expense, Project, User
from app.models.enums import BudgetCategory, UserRole


def make_user(
    db: Session, *, email: str = "user@example.com", role: UserRole = UserRole.RESEARCHER
) -> User:
    user = User(email=email, password_hash="x", name="테스트사용자", role=role)
    db.add(user)
    db.flush()
    return user


def make_project(db: Session, *, code: str = "P-2026-001") -> Project:
    project = Project(
        code=code,
        name="자율 지게차 인지 모듈 개발",
        agency="한국산업기술기획평가원",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
    )
    db.add(project)
    db.flush()
    return project


def make_budget(
    db: Session,
    project: Project,
    *,
    category: BudgetCategory = BudgetCategory.MATERIAL,
    amount: int = 10_000_000,
) -> Budget:
    budget = Budget(project_id=project.id, category=category, amount=Decimal(amount))
    db.add(budget)
    db.flush()
    return budget


def make_expense(
    db: Session,
    project: Project,
    user: User,
    *,
    category: BudgetCategory = BudgetCategory.MATERIAL,
    amount: int = 500_000,
    spent_at: date = date(2026, 3, 10),
) -> Expense:
    expense = Expense(
        project_id=project.id,
        category=category,
        created_by=user.id,
        title="시약 구입",
        vendor_name="테스트상사",
        vendor_biz_no="1234567890",
        amount=Decimal(amount),
        spent_at=spent_at,
    )
    db.add(expense)
    db.flush()
    return expense
