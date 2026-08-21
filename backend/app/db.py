"""데이터베이스 엔진/세션.

동기 SQLAlchemy를 사용한다. 내부 업무 시스템 규모에서는 async가 주는 이점보다
코드 단순성(트랜잭션 경계가 눈에 보이는 것)이 더 크다고 판단했다.
FastAPI는 sync 엔드포인트를 스레드풀에서 실행하므로 이벤트 루프를 막지 않는다.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

engine = create_engine(get_settings().database_url, pool_pre_ping=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI 의존성: 요청당 세션 1개, 요청 종료 시 반드시 닫는다."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
