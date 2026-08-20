"""골든 케이스 회귀 테스트 — 실제 Claude API를 호출한다 (opt-in).

실행:  ANTHROPIC_API_KEY=... pytest -m golden
목적:  프롬프트(app/ai/prompts.py)를 수정했을 때 기대 결과가 유지되는지 확인한다.
       프롬프트 변경 시 PROMPT_VERSION을 올리고 이 테스트를 돌려라.

증빙 이미지 골든 케이스 추가 방법:
  tests/golden/ 에 샘플 증빙 파일과 기대 추출값 JSON을 (같은 이름으로) 두면
  test_golden_extraction이 자동으로 대조한다. (실제 거래처 정보가 담긴 파일은 넣지 말 것)
"""

import json
import os
from pathlib import Path

import pytest

from app.models.enums import BudgetCategory

pytestmark = [
    pytest.mark.golden,
    pytest.mark.skipif(
        not os.environ.get("ANTHROPIC_API_KEY"), reason="ANTHROPIC_API_KEY 필요 (opt-in)"
    ),
]

GOLDEN_DIR = Path(__file__).parent / "golden"


def _client():
    from app.ai.anthropic_client import AnthropicAIClient

    return AnthropicAIClient()


@pytest.mark.parametrize(
    ("title", "vendor", "amount", "expected"),
    [
        ("시약 및 배양배지 구입", "바이오켐상사", 480_000, BudgetCategory.MATERIAL),
        ("학회 출장 KTX 왕복", "한국철도공사", 96_000, BudgetCategory.ACTIVITY),
        ("3D 프린터 장비 구입", "메이커테크", 3_200_000, BudgetCategory.EQUIPMENT),
    ],
)
def test_golden_category_suggestion(title, vendor, amount, expected) -> None:
    suggestion = _client().suggest_category(
        extraction=None, title=title, vendor_name=vendor, amount=amount
    )
    assert suggestion.category is expected, suggestion


def test_golden_extraction() -> None:
    samples = sorted(GOLDEN_DIR.glob("*.json")) if GOLDEN_DIR.exists() else []
    if not samples:
        pytest.skip("tests/golden/ 에 샘플 증빙+기대값이 없음")
    client = _client()
    for expected_path in samples:
        expected = json.loads(expected_path.read_text())
        source = next(
            p
            for p in GOLDEN_DIR.glob(f"{expected_path.stem}.*")
            if p.suffix in (".pdf", ".png", ".jpg")
        )
        mime = {
            ".pdf": "application/pdf",
            ".png": "image/png",
            ".jpg": "image/jpeg",
        }[source.suffix]
        result = client.extract_document(file_bytes=source.read_bytes(), mime_type=mime)
        assert result.total_amount == expected["total_amount"], expected_path.name
        assert result.biz_no == expected["biz_no"], expected_path.name
