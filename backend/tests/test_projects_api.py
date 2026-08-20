"""과제·예산 API 테스트."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.enums import UserRole
from tests.conftest import create_account, login_headers

PROJECT_BODY = {
    "code": "P-2026-001",
    "name": "자율 지게차 인지 모듈 개발",
    "agency": "한국산업기술기획평가원",
    "start_date": "2026-01-01",
    "end_date": "2026-12-31",
    "budgets": [
        {"category": "MATERIAL", "amount": 50000000},
        {"category": "ACTIVITY", "amount": 20000000},
    ],
}


def _admin_headers(client: TestClient, db: Session) -> dict[str, str]:
    create_account(db, email="admin@corp.kr", role=UserRole.ADMIN)
    return login_headers(client, "admin@corp.kr")


def test_create_project_with_budgets(client: TestClient, db: Session) -> None:
    headers = _admin_headers(client, db)

    res = client.post("/api/v1/projects", headers=headers, json=PROJECT_BODY)
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["code"] == "P-2026-001"
    material = next(b for b in body["budgets"] if b["category"] == "MATERIAL")
    # 아직 승인된 집행이 없으므로 잔액 == 예산
    assert material["approved"] == "0"
    assert material["remaining"] == "50000000"


def test_duplicate_project_code(client: TestClient, db: Session) -> None:
    headers = _admin_headers(client, db)
    client.post("/api/v1/projects", headers=headers, json=PROJECT_BODY)

    res = client.post("/api/v1/projects", headers=headers, json=PROJECT_BODY)
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "DUPLICATE"


def test_invalid_period_rejected(client: TestClient, db: Session) -> None:
    headers = _admin_headers(client, db)
    bad = {**PROJECT_BODY, "start_date": "2026-12-31", "end_date": "2026-01-01"}

    res = client.post("/api/v1/projects", headers=headers, json=bad)
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "VALIDATION_ERROR"


def test_researcher_can_list_projects(client: TestClient, db: Session) -> None:
    headers = _admin_headers(client, db)
    client.post("/api/v1/projects", headers=headers, json=PROJECT_BODY)
    create_account(db, email="r1@corp.kr", role=UserRole.RESEARCHER)

    res = client.get("/api/v1/projects", headers=login_headers(client, "r1@corp.kr"))
    assert res.status_code == 200
    assert len(res.json()) == 1


def test_update_project(client: TestClient, db: Session) -> None:
    headers = _admin_headers(client, db)
    project_id = client.post("/api/v1/projects", headers=headers, json=PROJECT_BODY).json()["id"]

    res = client.patch(
        f"/api/v1/projects/{project_id}", headers=headers, json={"status": "CLOSED"}
    )
    assert res.status_code == 200
    assert res.json()["status"] == "CLOSED"
