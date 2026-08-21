"""AnthropicAIClient 단위 테스트 — SDK를 스텁으로 대체해 요청 구성과 응답 변환을 검증한다.

실제 Claude API를 호출하는 골든 회귀 테스트는 test_golden.py (opt-in, -m golden).
"""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.ai.anthropic_client import (
    AnthropicAIClient,
    ExtractionOutput,
    SuggestionOutput,
    _normalize_biz_no,
    _parse_date,
)
from app.models.enums import BudgetCategory


@pytest.fixture
def client_with_stub(monkeypatch: pytest.MonkeyPatch):
    """API 키 없이 클라이언트를 만들고 SDK 호출을 기록·대체한다."""
    ai = AnthropicAIClient()
    calls: dict = {}

    def fake_parse(**kwargs):
        calls["parse"] = kwargs
        return SimpleNamespace(parsed_output=calls["parse_result"])

    def fake_create(**kwargs):
        calls["create"] = kwargs
        return SimpleNamespace(
            content=[
                SimpleNamespace(type="thinking", text=None),
                SimpleNamespace(type="text", text="## 요약\n집행 없음"),
            ]
        )

    ai._client = SimpleNamespace(
        messages=SimpleNamespace(parse=fake_parse, create=fake_create)
    )
    return ai, calls


def test_extract_pdf_uses_document_block(client_with_stub) -> None:
    ai, calls = client_with_stub
    calls["parse_result"] = ExtractionOutput(
        doc_type="세금계산서",
        vendor_name="테스트상사",
        biz_no="123-45-67891",
        total_amount=500_000,
        issued_at="2026-03-10",
        confidence=0.95,
    )

    result = ai.extract_document(file_bytes=b"%PDF-1.4", mime_type="application/pdf")

    sent_block = calls["parse"]["messages"][0]["content"][0]
    assert sent_block["type"] == "document"
    assert sent_block["source"]["media_type"] == "application/pdf"
    assert calls["parse"]["output_format"] is ExtractionOutput
    # 변환 검증: 하이픈 제거, ISO 날짜, Decimal confidence
    assert result.biz_no == "1234567891"
    assert result.issued_at == date(2026, 3, 10)
    assert result.confidence == Decimal("0.95")


def test_extract_image_uses_image_block(client_with_stub) -> None:
    ai, calls = client_with_stub
    calls["parse_result"] = ExtractionOutput(
        doc_type=None,
        vendor_name=None,
        biz_no=None,
        total_amount=None,
        issued_at=None,
        confidence=0.2,
    )

    result = ai.extract_document(file_bytes=b"\x89PNG", mime_type="image/png")

    sent_block = calls["parse"]["messages"][0]["content"][0]
    assert sent_block["type"] == "image"
    assert sent_block["source"]["media_type"] == "image/png"
    assert result.total_amount is None


def test_suggest_category_maps_to_enum(client_with_stub) -> None:
    ai, calls = client_with_stub
    calls["parse_result"] = SuggestionOutput(
        category="MATERIAL", confidence=0.88, rationale="시약 구입은 연구재료비"
    )

    suggestion = ai.suggest_category(
        extraction=None,
        title="시약 구입",
        vendor_name="테스트상사",
        amount=500_000,
        purpose="인지 모듈 성능시험용",
    )

    assert suggestion.category is BudgetCategory.MATERIAL
    assert suggestion.confidence == Decimal("0.88")
    assert "시약 구입" in calls["parse"]["messages"][0]["content"]
    # 사용 용도가 프롬프트에 실제로 들어가는지 — 비목은 용도로 갈린다
    assert "인지 모듈 성능시험용" in calls["parse"]["messages"][0]["content"]


def test_narrative_joins_text_blocks_only(client_with_stub) -> None:
    ai, calls = client_with_stub

    text = ai.draft_report_narrative(summary={"totals": {"budget": 1}})

    assert text == "## 요약\n집행 없음"
    assert "1" in calls["create"]["messages"][0]["content"]  # 집계 JSON이 전달됨


def test_defensive_parsers() -> None:
    assert _normalize_biz_no("123-45-67891") == "1234567891"
    assert _normalize_biz_no("12345") is None  # 10자리가 아니면 버린다
    assert _normalize_biz_no(None) is None
    assert _parse_date("2026-03-10") == date(2026, 3, 10)
    assert _parse_date("2026/03/10") is None  # 형식 위반은 None (파이프라인 보호)
    assert _parse_date(None) is None
