"""테스트 공통 픽스처.

실제 PostgreSQL(settlement_hub_test)에 Alembic 마이그레이션을 적용해 테스트한다.
SQLite 대체 없이 실 DB를 쓰는 이유: JSONB, native enum, FOR UPDATE SKIP LOCKED 등
이 프로젝트의 핵심 동작이 PG 전용이기 때문이다.
"""

import os
import tempfile

# app 모듈 import 전에 테스트 DB URL을 고정한다 (app.db가 import 시점에 엔진을 만든다)
os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://dev:dev@localhost:5432/settlement_hub_test"
)
# HS256 권장 키 길이(32바이트+)를 충족하는 테스트 전용 시크릿
os.environ.setdefault("SECRET_KEY", "test-secret-key-0123456789abcdef0123456789abcdef")
# 증빙 업로드는 임시 디렉토리에 저장
os.environ.setdefault("UPLOAD_DIR", tempfile.mkdtemp(prefix="settlement-hub-test-uploads-"))

from collections.abc import Generator  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.db import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base, User  # noqa: E402
from app.models.enums import UserRole  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parent.parent

# 테스트 사용자 공통 비밀번호. bcrypt는 느리므로 해시를 1회만 계산해 재사용한다.
TEST_PASSWORD = "test-password-1"
TEST_PASSWORD_HASH = hash_password(TEST_PASSWORD)


@pytest.fixture(scope="session", autouse=True)
def apply_migrations() -> Generator[None, None, None]:
    """테스트 세션 시작 시 마이그레이션을 밑바닥부터 적용한다.

    (스키마 정의가 아니라 '마이그레이션 파일'이 검증 대상이므로
    Base.metadata.create_all 대신 alembic을 실제로 실행한다)
    """
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    yield


@pytest.fixture
def db() -> Generator[Session, None, None]:
    """함수 스코프 세션. 테스트 종료 시 모든 테이블을 비워 테스트 간 격리를 보장한다."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        table_names = ", ".join(t.name for t in Base.metadata.sorted_tables)
        with engine.begin() as conn:
            conn.execute(text(f"TRUNCATE {table_names} RESTART IDENTITY CASCADE"))


@pytest.fixture
def client(db: Session) -> Generator[TestClient, None, None]:
    """API 테스트 클라이언트. 앱과 테스트가 같은 테스트 DB를 바라본다."""
    with TestClient(app) as c:
        yield c


def create_account(db: Session, *, email: str, role: UserRole) -> User:
    """API 테스트용 계정 생성 (비밀번호는 TEST_PASSWORD)."""
    user = User(email=email, password_hash=TEST_PASSWORD_HASH, name="테스트", role=role)
    db.add(user)
    db.commit()
    return user


def login_headers(client: TestClient, email: str) -> dict[str, str]:
    """로그인 후 Authorization 헤더를 만든다."""
    res = client.post("/api/v1/auth/login", json={"email": email, "password": TEST_PASSWORD})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}
