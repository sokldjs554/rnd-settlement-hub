"""공휴일 판정 + 한국천문연구원 특일 API 동기화.

룰 평가는 로컬 holidays 테이블만 본다(외부 API 의존을 평가 경로에서 분리).
테이블은 KASI 특일 API(getRestDeInfo)로 연 단위 동기화하거나 시드로 채운다.

동기화 CLI:  python -m app.external.holidays 2026
"""

import logging
import sys
from datetime import date, datetime

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Holiday

logger = logging.getLogger(__name__)

KASI_REST_DE_URL = (
    "http://apis.data.go.kr/B090041/openapi/service/SpcdeInfoService/getRestDeInfo"
)


def is_nonworking_day(db: Session, d: date) -> bool | None:
    """주말·공휴일 여부. 해당 연도 데이터가 없으면 None(정보 없음 — 룰은 판정을 보류한다)."""
    if d.weekday() >= 5:  # 토(5)·일(6)
        return True
    if db.get(Holiday, d) is not None:
        return True
    year_count = db.execute(
        select(func.count())
        .select_from(Holiday)
        .where(Holiday.date >= date(d.year, 1, 1), Holiday.date <= date(d.year, 12, 31))
    ).scalar_one()
    if year_count == 0:
        return None  # 이 연도는 동기화된 적이 없다
    return False


def sync_year(db: Session, year: int) -> int:
    """KASI 특일 API로 해당 연도 공휴일을 동기화한다. 반환: 저장된 건수 (commit 포함)."""
    api_key = get_settings().kasi_api_key
    if not api_key:
        logger.warning("KASI_API_KEY 미설정 — 공휴일 동기화 생략")
        return 0

    saved = 0
    for month in range(1, 13):
        try:
            response = httpx.get(
                KASI_REST_DE_URL,
                params={
                    "serviceKey": api_key,
                    "solYear": year,
                    "solMonth": f"{month:02d}",
                    "_type": "json",
                    "numOfRows": 30,
                },
                timeout=10.0,
            )
            response.raise_for_status()
            body = response.json()["response"]["body"]
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            logger.warning("KASI API 실패 (%d-%02d): %s", year, month, exc)
            continue

        items = body.get("items") or {}
        rows = items.get("item") if isinstance(items, dict) else None
        if rows is None:
            continue
        if isinstance(rows, dict):  # 결과 1건이면 dict로 온다
            rows = [rows]
        for row in rows:
            if row.get("isHoliday") != "Y":
                continue
            holiday_date = datetime.strptime(str(row["locdate"]), "%Y%m%d").date()
            if db.get(Holiday, holiday_date) is None:
                db.add(Holiday(date=holiday_date, name=row.get("dateName", ""), source="KASI"))
                saved += 1
    db.commit()
    return saved


if __name__ == "__main__":
    from app.db import SessionLocal

    logging.basicConfig(level=logging.INFO)
    target_year = int(sys.argv[1]) if len(sys.argv) > 1 else date.today().year
    with SessionLocal() as session:
        count = sync_year(session, target_year)
        print(f"{target_year}년 공휴일 {count}건 동기화 완료")
