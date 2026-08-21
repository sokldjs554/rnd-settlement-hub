"""인증·권한 API 테스트."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.enums import UserRole
from tests.conftest import TEST_PASSWORD, create_account, login_headers


def test_login_and_me(client: TestClient, db: Session) -> None:
    create_account(db, email="r1@corp.kr", role=UserRole.RESEARCHER)

    res = client.post("/api/v1/auth/login", json={"email": "r1@corp.kr", "password": TEST_PASSWORD})
    assert res.status_code == 200
    body = res.json()
    assert body["user"]["role"] == "RESEARCHER"
    # refresh 토큰은 httpOnly 쿠키로만 내려간다
    assert "refresh_token" in res.cookies

    me = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"}
    )
    assert me.status_code == 200
    assert me.json()["email"] == "r1@corp.kr"


def test_login_wrong_password_returns_standard_envelope(
    client: TestClient, db: Session
) -> None:
    create_account(db, email="r1@corp.kr", role=UserRole.RESEARCHER)

    res = client.post("/api/v1/auth/login", json={"email": "r1@corp.kr", "password": "wrong"})
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_me_without_token(client: TestClient) -> None:
    res = client.get("/api/v1/auth/me")
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "UNAUTHORIZED"


def test_refresh_rotates_and_issues_new_access_token(client: TestClient, db: Session) -> None:
    create_account(db, email="r1@corp.kr", role=UserRole.RESEARCHER)
    client.post("/api/v1/auth/login", json={"email": "r1@corp.kr", "password": TEST_PASSWORD})

    res = client.post("/api/v1/auth/refresh")  # TestClient가 쿠키를 유지한다
    assert res.status_code == 200
    assert res.json()["access_token"]


def test_rbac_researcher_cannot_create_project(client: TestClient, db: Session) -> None:
    create_account(db, email="r1@corp.kr", role=UserRole.RESEARCHER)
    headers = login_headers(client, "r1@corp.kr")

    res = client.post(
        "/api/v1/projects",
        headers=headers,
        json={
            "code": "P-1",
            "name": "n",
            "agency": "a",
            "start_date": "2026-01-01",
            "end_date": "2026-12-31",
            "budgets": [{"category": "MATERIAL", "amount": 1000}],
        },
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "FORBIDDEN"


def test_health_reports_integration_flags(client: TestClient) -> None:
    """헬스체크는 외부 연동 설정 여부만 알려주고 키 값은 노출하지 않는다."""
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    # 테스트 환경엔 키가 없으므로 전부 False
    assert body["integrations"] == {"ai": False, "nts": False, "kasi": False}
    assert "key" not in res.text.lower()
