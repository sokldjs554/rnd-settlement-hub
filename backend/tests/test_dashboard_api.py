"""대시보드·알림 API 테스트."""

from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import AiRun
from app.models.enums import (
    AiRunKind,
    AiRunStatus,
    BudgetCategory,
    ExpenseStatus,
    UserRole,
)
from tests.conftest import create_account, login_headers
from tests.factories import make_budget, make_expense, make_project, make_user


def test_dashboard_summary(client: TestClient, db: Session) -> None:
    project = make_project(db)
    make_budget(db, project, amount=10_000_000)
    researcher = make_user(db, email="r@corp.kr")
    approved = make_expense(db, project, researcher, amount=1_000_000, spent_at=date(2026, 3, 5))
    approved.status = ExpenseStatus.APPROVED
    pending = make_expense(db, project, researcher, amount=200_000)
    pending.status = ExpenseStatus.NEEDS_REVIEW
    # AI 제안 기록: 채택 1건 (suggested == 확정 category)
    db.add(
        AiRun(
            expense_id=approved.id,
            kind=AiRunKind.CATEGORY_SUGGESTION,
            model="fake",
            prompt_version="v1",
            status=AiRunStatus.SUCCESS,
            suggested_category=BudgetCategory.MATERIAL,
            confidence=Decimal("0.9"),
        )
    )
    db.commit()
    create_account(db, email="mgr@corp.kr", role=UserRole.MANAGER)
    headers = login_headers(client, "mgr@corp.kr")

    res = client.get("/api/v1/dashboard/summary", headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()

    material = next(b for b in body["budget_usage"] if b["category"] == "MATERIAL")
    assert material["approved"] == "1000000"
    statuses = {s["status"]: s for s in body["status_counts"]}
    assert statuses["NEEDS_REVIEW"]["count"] == 1
    assert body["ai_metrics"]["suggestion_adoption_rate"] == 1.0
    assert body["automation_effect"]["assumed_manual_minutes_per_case"] == 15


def test_dashboard_requires_manager(client: TestClient, db: Session) -> None:
    create_account(db, email="r@corp.kr", role=UserRole.RESEARCHER)
    res = client.get("/api/v1/dashboard/summary", headers=login_headers(client, "r@corp.kr"))
    assert res.status_code == 403


def test_notifications_flow(client: TestClient, db: Session) -> None:
    from app.services.notification import notify

    user = create_account(db, email="mgr@corp.kr", role=UserRole.MANAGER)
    notify(db, user.id, "expense_needs_review", {"expense_id": 1})
    db.commit()
    headers = login_headers(client, "mgr@corp.kr")

    unread = client.get("/api/v1/notifications?unread=true", headers=headers).json()
    assert len(unread) == 1

    marked = client.patch(f"/api/v1/notifications/{unread[0]['id']}/read", headers=headers)
    assert marked.status_code == 200
    assert marked.json()["read_at"] is not None

    assert client.get("/api/v1/notifications?unread=true", headers=headers).json() == []
