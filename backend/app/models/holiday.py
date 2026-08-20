from datetime import date, datetime

from sqlalchemy import Date, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Holiday(Base):
    """공휴일 로컬 캐시.

    R-DAY-001(주말·공휴일 집행) 룰이 참조한다. 한국천문연구원 특일 API로 연 단위 동기화하며,
    API 없이도 시드 데이터로 동작한다 — 외부 API 의존을 룰 평가 경로에서 분리하기 위한 테이블.
    """

    __tablename__ = "holidays"

    date: Mapped[date] = mapped_column(Date, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="KASI")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
