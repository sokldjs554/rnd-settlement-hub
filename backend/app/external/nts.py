"""국세청 사업자등록 상태조회 (공공데이터포털).

API: POST https://api.odcloud.kr/api/nts-businessman/v1/status?serviceKey=...
     body {"b_no": ["1234567890"]} → data[0].b_stt_cd: 01 계속 / 02 휴업 / 03 폐업
     (미등록 번호는 b_stt_cd가 비고 tax_type에 안내 문구가 온다)
쿼터: 호출당 100건, 일 100만 건.

장애 대응 원칙(면접 질문 "외부 API가 다운되면?"의 답):
- 결과를 vendor_checks에 캐시(TTL 30일) → 같은 거래처 반복 조회 방지 + 장애 시 폴백
- 호출 실패 시: 캐시가 있으면 오래됐어도 그 값을 쓰고, 없으면 UNVERIFIED 반환
  → 워크플로는 절대 멈추지 않고, R-VND-003 WARN이 수기 확인을 요구한다
"""

import logging
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import VendorCheck
from app.models.enums import VendorStatus

logger = logging.getLogger(__name__)

NTS_STATUS_URL = "https://api.odcloud.kr/api/nts-businessman/v1/status"
CACHE_TTL = timedelta(days=30)
TIMEOUT_SECONDS = 5.0

_STATUS_CODE_MAP = {
    "01": VendorStatus.ACTIVE,
    "02": VendorStatus.SUSPENDED,
    "03": VendorStatus.CLOSED,
}


def check_vendor_status(db: Session, biz_no: str) -> VendorStatus:
    """사업자 상태를 반환한다 (캐시 우선, 필요 시 API 호출). commit은 호출자 몫."""
    cached = db.execute(
        select(VendorCheck).where(VendorCheck.biz_no == biz_no)
    ).scalar_one_or_none()

    now = datetime.now(UTC)
    if (
        cached is not None
        and cached.status != VendorStatus.UNVERIFIED
        and cached.checked_at > now - CACHE_TTL
    ):
        return cached.status

    fetched = _fetch_from_api(biz_no)
    if fetched is None:
        # API 실패: 오래된 캐시라도 있으면 그 값을 신뢰(휴폐업 상태는 급변하지 않는다)
        if cached is not None and cached.status != VendorStatus.UNVERIFIED:
            logger.warning("NTS API 실패 — %s의 캐시값(%s) 사용", biz_no, cached.status)
            return cached.status
        _upsert(db, cached, biz_no, VendorStatus.UNVERIFIED, raw=None, now=now)
        return VendorStatus.UNVERIFIED

    status, raw = fetched
    _upsert(db, cached, biz_no, status, raw=raw, now=now)
    return status


def _fetch_from_api(biz_no: str) -> tuple[VendorStatus, dict] | None:
    """API 1회 호출. 실패(네트워크/쿼터/파싱)는 None으로 통일한다."""
    api_key = get_settings().nts_api_key
    if not api_key:
        return None
    try:
        response = httpx.post(
            NTS_STATUS_URL,
            params={"serviceKey": api_key},
            json={"b_no": [biz_no]},
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        item = response.json()["data"][0]
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
        logger.warning("NTS API 호출 실패 (biz_no=%s): %s", biz_no, exc)
        return None

    code = item.get("b_stt_cd", "")
    status = _STATUS_CODE_MAP.get(code, VendorStatus.UNREGISTERED)
    return status, item


def _upsert(
    db: Session,
    cached: VendorCheck | None,
    biz_no: str,
    status: VendorStatus,
    *,
    raw: dict | None,
    now: datetime,
) -> None:
    if cached is None:
        db.add(
            VendorCheck(
                biz_no=biz_no,
                status=status,
                b_stt=(raw or {}).get("b_stt") or None,
                tax_type=(raw or {}).get("tax_type") or None,
                end_dt=(raw or {}).get("end_dt") or None,
                checked_at=now,
                raw=raw,
            )
        )
    else:
        cached.status = status
        cached.b_stt = (raw or {}).get("b_stt") or None
        cached.tax_type = (raw or {}).get("tax_type") or None
        cached.end_dt = (raw or {}).get("end_dt") or None
        cached.checked_at = now
        cached.raw = raw
    db.flush()
