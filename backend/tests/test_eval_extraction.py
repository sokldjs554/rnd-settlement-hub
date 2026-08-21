"""AI 추출 벤치마크(eval_extraction)의 채점 로직 테스트 — 실제 API 호출 없음."""

from datetime import date
from decimal import Decimal
from pathlib import Path

from app.ai.base import ExtractedDoc
from app.eval_extraction import compare_field, normalize_vendor, run, score_document
from tests.fakes import FakeAIClient

EVAL_DIR = Path(__file__).parent.parent / "eval"

LABEL = {
    "file": "x.png",
    "tier": "easy",
    "doc_type": "card",
    "vendor_name": "(주)가온바이오",
    "biz_no": "1018116293",
    "total_amount": 1_320_000,
    "issued_at": "2026-08-20",
}


def make_doc(**overrides) -> ExtractedDoc:
    base = dict(
        doc_type="카드전표",
        vendor_name="(주)가온바이오",
        biz_no="1018116293",
        total_amount=1_320_000,
        issued_at=date(2026, 8, 20),
        confidence=Decimal("0.9"),
    )
    return ExtractedDoc(**{**base, **overrides})


class TestCompareField:
    def test_vendor_normalization_ignores_corp_prefix_and_spaces(self) -> None:
        assert normalize_vendor("(주) 가온바이오") == normalize_vendor("주식회사 가온바이오")
        assert compare_field("vendor_name", "(주)가온바이오", "가온 바이오") == "correct"

    def test_golden_null_and_model_null_is_correct_abstention(self) -> None:
        assert compare_field("total_amount", None, None) == "abstained"

    def test_golden_null_but_model_answers_is_hallucination(self) -> None:
        assert compare_field("total_amount", None, 999_999) == "hallucinated"

    def test_model_null_on_existing_answer_is_missed(self) -> None:
        assert compare_field("biz_no", "1018116293", None) == "missed"

    def test_date_object_matches_iso_string(self) -> None:
        assert compare_field("issued_at", "2026-08-20", date(2026, 8, 20)) == "correct"


class TestScoreDocument:
    def test_perfect_extraction(self) -> None:
        verdicts = score_document(LABEL, make_doc())
        assert all(v == "correct" for v in verdicts.values())

    def test_wrong_amount_detected(self) -> None:
        verdicts = score_document(LABEL, make_doc(total_amount=1_200_000))
        assert verdicts["total_amount"] == "wrong"
        assert verdicts["biz_no"] == "correct"


class TestRunReport:
    def test_report_renders_against_real_fixture_set(self) -> None:
        """저장소에 커밋된 fixtures/labels.json과 스크립트가 맞물리는지 확인한다."""
        report = run(FakeAIClient(), EVAL_DIR, limit=3)
        assert "필드별 결과" in report
        assert "fake-model" in report
        # FakeAIClient는 고정값을 돌려주므로 대부분 오답 → 오류 상세 표가 나와야 한다
        assert "오류 상세" in report

    def test_fixture_set_is_complete(self) -> None:
        import json

        labels = json.loads((EVAL_DIR / "labels.json").read_text())
        assert len(labels) == 25
        for label in labels:
            assert (EVAL_DIR / "receipts" / label["file"]).exists()
