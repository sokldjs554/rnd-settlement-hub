"""정산보고서 API 테스트: 집계 정확성, AI 초안 워커, 확정 잠금."""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

import app.services.report as report_module
from app.models import AiRun, Expense, Report
from app.models.enums import AiRunKind, ExpenseStatus, UserRole
from app.services import queue
from app.worker import execute
from tests.conftest import create_account, login_headers
from tests.factories import make_budget, make_expense, make_project, make_user

VALID_BIZ_NO = "1234567891"


def _seed(db: Session) -> dict:
    project = make_project(db)
    make_budget(db, project, amount=10_000_000)  # MATERIAL
    researcher = make_user(db, email="r@corp.kr")
    # 3월 승인 2건(합 1,200,000), 2월 승인 1건(300,000), 3월 반려 1건
    for amount, spent, status in [
        (500_000, date(2026, 3, 10), ExpenseStatus.APPROVED),
        (700_000, date(2026, 3, 20), ExpenseStatus.APPROVED),
        (300_000, date(2026, 2, 5), ExpenseStatus.APPROVED),
        (100_000, date(2026, 3, 15), ExpenseStatus.REJECTED),
    ]:
        e = make_expense(db, project, researcher, amount=amount, spent_at=spent)
        e.status = status
    db.commit()
    return {"project_id": project.id}


def _manager_headers(client: TestClient, db: Session) -> dict[str, str]:
    create_account(db, email="mgr@corp.kr", role=UserRole.MANAGER)
    return login_headers(client, "mgr@corp.kr")


def test_report_summary_numbers_come_from_sql(client: TestClient, db: Session) -> None:
    ctx = _seed(db)
    headers = _manager_headers(client, db)

    res = client.post(
        f"/api/v1/projects/{ctx['project_id']}/reports",
        headers=headers,
        json={"year": 2026, "month": 3},
    )
    assert res.status_code == 201, res.text
    summary = res.json()["summary_json"]

    material = next(c for c in summary["categories"] if c["category"] == "MATERIAL")
    assert material["month_approved"] == 1_200_000  # 3월분만
    assert material["cumulative_approved"] == 1_500_000  # 2월 + 3월
    assert material["remaining"] == 8_500_000
    assert summary["counts"]["month_approved_count"] == 2
    assert summary["counts"]["month_rejected_count"] == 1


def test_duplicate_report_conflict(client: TestClient, db: Session) -> None:
    ctx = _seed(db)
    headers = _manager_headers(client, db)
    body = {"year": 2026, "month": 3}
    client.post(f"/api/v1/projects/{ctx['project_id']}/reports", headers=headers, json=body)

    res = client.post(
        f"/api/v1/projects/{ctx['project_id']}/reports", headers=headers, json=body
    )
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "DUPLICATE"


def test_worker_fills_ai_narrative_draft(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.fakes import FakeAIClient

    fake = FakeAIClient(narrative="3월은 연구재료비 집행이 집중되었습니다.")
    monkeypatch.setattr(report_module, "get_ai_client", lambda: fake)

    ctx = _seed(db)
    headers = _manager_headers(client, db)
    report_id = client.post(
        f"/api/v1/projects/{ctx['project_id']}/reports",
        headers=headers,
        json={"year": 2026, "month": 3},
    ).json()["id"]

    run = queue.claim_next(db)
    assert run is not None and run.report_id == report_id
    execute(db, run)

    db.expire_all()
    report = db.get(Report, report_id)
    assert report is not None
    assert report.narrative_md == "3월은 연구재료비 집행이 집중되었습니다."
    ai_run = db.execute(
        select(AiRun).where(AiRun.report_id == report_id)
    ).scalar_one()
    assert ai_run.kind == AiRunKind.REPORT_NARRATIVE


def test_worker_without_ai_leaves_narrative_empty(client: TestClient, db: Session) -> None:
    """AI 키가 없어도 보고서(집계)는 완성 — 서술만 비어 있고 담당자가 직접 쓴다."""
    ctx = _seed(db)
    headers = _manager_headers(client, db)
    report_id = client.post(
        f"/api/v1/projects/{ctx['project_id']}/reports",
        headers=headers,
        json={"year": 2026, "month": 3},
    ).json()["id"]

    run = queue.claim_next(db)
    assert run is not None
    execute(db, run)  # NullAIClient → AIUnavailableError → 초안 없이 정상 종료

    db.expire_all()
    report = db.get(Report, report_id)
    assert report is not None and report.narrative_md is None
    assert run.status.value == "SUCCEEDED"


def test_finalize_locks_expenses(client: TestClient, db: Session) -> None:
    ctx = _seed(db)
    headers = _manager_headers(client, db)
    report_id = client.post(
        f"/api/v1/projects/{ctx['project_id']}/reports",
        headers=headers,
        json={"year": 2026, "month": 3},
    ).json()["id"]

    res = client.post(f"/api/v1/reports/{report_id}/finalize", headers=headers)
    assert res.status_code == 200
    assert res.json()["status"] == "FINAL"

    # 3월 승인 건 2건이 보고서에 묶였다 (2월 건은 제외)
    locked = db.execute(
        select(Expense).where(Expense.report_id == report_id)
    ).scalars().all()
    assert len(locked) == 2

    # 묶인 건은 수정 불가
    create_account(db, email="r2@corp.kr", role=UserRole.RESEARCHER)
    expense_id = locked[0].id
    owner_headers = headers  # MANAGER도 잠금은 우회 못 한다
    patch = client.patch(
        f"/api/v1/expenses/{expense_id}", headers=owner_headers, json={"amount": 1}
    )
    assert patch.status_code == 409
    assert patch.json()["error"]["code"] == "EXPENSE_LOCKED"

    # 확정 보고서 서술 수정·재확정 불가
    assert (
        client.patch(
            f"/api/v1/reports/{report_id}", headers=headers, json={"narrative_md": "x"}
        ).status_code
        == 409
    )
    assert (
        client.post(f"/api/v1/reports/{report_id}/finalize", headers=headers).status_code == 409
    )


def test_report_requires_manager(client: TestClient, db: Session) -> None:
    ctx = _seed(db)
    create_account(db, email="r9@corp.kr", role=UserRole.RESEARCHER)
    headers = login_headers(client, "r9@corp.kr")

    res = client.post(
        f"/api/v1/projects/{ctx['project_id']}/reports",
        headers=headers,
        json={"year": 2026, "month": 3},
    )
    assert res.status_code == 403
