"""국세청 상태조회 클라이언트 테스트 — 캐시·장애 폴백 동작 검증 (실 API 호출 없음)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.external import nts
from app.models import VendorCheck
from app.models.enums import VendorStatus

BIZ_NO = "1234567891"


@pytest.fixture(autouse=True)
def fake_api_key(monkeypatch: pytest.MonkeyPatch):
    """설정 캐시(lru_cache)를 우회해 API 키가 있는 상태를 만든다."""
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "nts_api_key", "test-key")
    yield
    monkeypatch.setattr(get_settings(), "nts_api_key", "")


def mock_api(monkeypatch: pytest.MonkeyPatch, item: dict | Exception) -> list:
    """httpx.post를 대체한다. item이 Exception이면 호출 실패를 재현한다."""
    calls: list = []

    class FakeResponse:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            return {"data": [item]}

    def fake_post(*args, **kwargs):
        calls.append(kwargs)
        if isinstance(item, Exception):
            raise item
        return FakeResponse()

    monkeypatch.setattr(nts.httpx, "post", fake_post)
    return calls


def test_active_vendor_cached(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = mock_api(
        monkeypatch,
        {"b_stt": "계속사업자", "b_stt_cd": "01", "tax_type": "부가가치세 일반과세자"},
    )

    assert nts.check_vendor_status(db, BIZ_NO) == VendorStatus.ACTIVE
    db.commit()
    assert len(calls) == 1

    # 두 번째 조회는 캐시를 쓴다 (API 재호출 없음)
    assert nts.check_vendor_status(db, BIZ_NO) == VendorStatus.ACTIVE
    assert len(calls) == 1


def test_closed_and_unregistered_mapping(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    mock_api(monkeypatch, {"b_stt": "폐업자", "b_stt_cd": "03", "end_dt": "20250131"})
    assert nts.check_vendor_status(db, BIZ_NO) == VendorStatus.CLOSED
    row = db.execute(select(VendorCheck).where(VendorCheck.biz_no == BIZ_NO)).scalar_one()
    assert row.end_dt == "20250131"

    mock_api(
        monkeypatch,
        {"b_stt": "", "b_stt_cd": "", "tax_type": "국세청에 등록되지 않은 사업자등록번호입니다."},
    )
    assert nts.check_vendor_status(db, "9999999999") == VendorStatus.UNREGISTERED


def test_api_failure_without_cache_returns_unverified(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    import httpx

    mock_api(monkeypatch, httpx.ConnectTimeout("timeout"))
    assert nts.check_vendor_status(db, BIZ_NO) == VendorStatus.UNVERIFIED


def test_api_failure_falls_back_to_stale_cache(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """TTL이 지난 캐시라도 API 장애 시에는 그 값을 신뢰한다 — 워크플로를 막지 않기 위해."""
    import httpx

    db.add(
        VendorCheck(
            biz_no=BIZ_NO,
            status=VendorStatus.ACTIVE,
            checked_at=datetime.now(UTC) - timedelta(days=90),  # TTL(30일) 경과
        )
    )
    db.commit()

    mock_api(monkeypatch, httpx.ConnectTimeout("timeout"))
    assert nts.check_vendor_status(db, BIZ_NO) == VendorStatus.ACTIVE
