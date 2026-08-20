"""테스트 공통 픽스처.

실제 PostgreSQL(settlement_hub_test)에 Alembic 마이그레이션을 적용해 테스트한다.
SQLite 대체 없이 실 DB를 쓰는 이유: JSONB, native enum, FOR UPDATE SKIP LOCKED 등
이 프로젝트의 핵심 동작이 PG 전용이기 때문이다.
"""

import os

# app 모듈 import 전에 테스트 DB URL을 고정한다 (app.db가 import 시점에 엔진을 만든다)
os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://dev:dev@localhost:5432/settlement_hub_test"
)

from collections.abc import Generator  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db import SessionLocal, engine  # noqa: E402
from app.models import Base  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parent.parent


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
