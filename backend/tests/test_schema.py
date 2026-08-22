"""스키마 제약 검증: 마이그레이션으로 만든 실제 DB가 설계대로 동작하는지 확인한다."""

from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import AiRun, AutomationRun, Budget
from app.models.enums import (
    AiRunKind,
    AiRunStatus,
    AutomationKind,
    BudgetCategory,
    ExpenseStatus,
)
from tests.factories import make_budget, make_expense, make_project, make_user


def test_expense_defaults(db: Session) -> None:
    """신규 집행 건은 DRAFT 상태로 시작하고 타임스탬프가 자동 기록된다."""
    user = make_user(db)
    project = make_project(db)
    expense = make_expense(db, project, user)
    db.commit()

    assert expense.status == ExpenseStatus.DRAFT
    assert expense.created_at is not None
    assert expense.deleted_at is None


def test_budget_unique_per_project_category(db: Session) -> None:
    """같은 과제에 같은 비목 예산을 두 번 넣을 수 없다."""
    project = make_project(db)
    make_budget(db, project, category=BudgetCategory.MATERIAL)
    db.commit()

    with pytest.raises(IntegrityError):
        db.add(
            Budget(
                project_id=project.id,
                category=BudgetCategory.MATERIAL,
                amount=Decimal(1),
            )
        )
        db.commit()


def test_expense_amount_must_be_positive(db: Session) -> None:
    """CHECK 제약: 집행 금액은 0보다 커야 한다."""
    user = make_user(db)
    project = make_project(db)

    with pytest.raises(IntegrityError):
        make_expense(db, project, user, amount=0)
        db.commit()


def test_automation_run_idempotency_key_unique(db: Session) -> None:
    """같은 idempotency_key로 작업을 중복 등록할 수 없다 (중복 실행 방지 1차 방어선)."""
    user = make_user(db)
    project = make_project(db)
    expense = make_expense(db, project, user)

    db.add(
        AutomationRun(
            kind=AutomationKind.EXPENSE_PIPELINE,
            expense_id=expense.id,
            idempotency_key=f"expense:{expense.id}:pipeline:1",
        )
    )
    db.commit()

    with pytest.raises(IntegrityError):
        db.add(
            AutomationRun(
                kind=AutomationKind.EXPENSE_PIPELINE,
                expense_id=expense.id,
                idempotency_key=f"expense:{expense.id}:pipeline:1",
            )
        )
        db.commit()


def test_automation_run_requires_exactly_one_target(db: Session) -> None:
    """CHECK 제약: 작업 대상은 집행 건 또는 보고서 중 정확히 하나."""
    with pytest.raises(IntegrityError):
        db.add(
            AutomationRun(
                kind=AutomationKind.EXPENSE_PIPELINE,
                expense_id=None,
                report_id=None,
                idempotency_key="no-target",
            )
        )
        db.commit()


def test_ai_run_confidence_range(db: Session) -> None:
    """CHECK 제약: AI confidence는 0~1 범위."""
    user = make_user(db)
    project = make_project(db)
    expense = make_expense(db, project, user)

    with pytest.raises(IntegrityError):
        db.add(
            AiRun(
                expense_id=expense.id,
                kind=AiRunKind.DOC_EXTRACTION,
                model="claude-opus-5",
                prompt_version="v1",
                status=AiRunStatus.SUCCESS,
                confidence=Decimal("1.5"),
            )
        )
        db.commit()


def test_expense_cascade_deletes_children(db: Session) -> None:
    """집행 건 hard delete 시 증빙·검증 결과 등 자식 행이 함께 정리된다 (FK CASCADE).

    실제 운영에서는 soft delete(deleted_at)를 쓰지만, FK 무결성은 스키마 레벨에서 보장한다.
    """
    user = make_user(db)
    project = make_project(db)
    expense = make_expense(db, project, user)
    db.add(
        AiRun(
            expense_id=expense.id,
            kind=AiRunKind.DOC_EXTRACTION,
            model="claude-opus-5",
            prompt_version="v1",
            status=AiRunStatus.FAILED,
            error="test",
        )
    )
    db.commit()

    db.delete(expense)
    db.commit()

    assert db.query(AiRun).count() == 0


class TestDatabaseUrlNormalization:
    """관리형 Postgres가 주는 URL을 psycopg(v3)로 정규화하는지 확인한다.

    배포 시 접두어를 손으로 바꾸는 단계를 없애기 위한 것 — 이게 깨지면
    운영 환경에서 psycopg2를 찾다가 기동에 실패한다.
    """

    def test_bare_postgresql_scheme_gets_psycopg_driver(self) -> None:
        from app.config import Settings

        s = Settings(database_url="postgresql://u:p@host/db?sslmode=require")
        assert s.database_url == "postgresql+psycopg://u:p@host/db?sslmode=require"

    def test_legacy_postgres_scheme_is_normalized_too(self) -> None:
        from app.config import Settings

        s = Settings(database_url="postgres://u:p@host/db")
        assert s.database_url == "postgresql+psycopg://u:p@host/db"

    def test_explicit_driver_is_left_alone(self) -> None:
        from app.config import Settings

        url = "postgresql+asyncpg://u:p@host/db"
        assert Settings(database_url=url).database_url == url
