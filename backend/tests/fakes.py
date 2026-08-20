"""테스트용 AI 클라이언트 구현체."""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from app.ai.base import CategorySuggestion, ExtractedDoc
from app.models.enums import BudgetCategory


@dataclass
class FakeAIClient:
    """지정한 값을 그대로 돌려주는 AI 클라이언트. 호출 여부·인자를 기록한다."""

    extraction: ExtractedDoc = field(
        default_factory=lambda: ExtractedDoc(
            doc_type="세금계산서",
            vendor_name="테스트상사",
            biz_no="1234567891",
            total_amount=500_000,
            issued_at=date(2026, 3, 10),
            confidence=Decimal("0.95"),
        )
    )
    suggestion: CategorySuggestion = field(
        default_factory=lambda: CategorySuggestion(
            category=BudgetCategory.MATERIAL,
            confidence=Decimal("0.9"),
            rationale="시약 구입은 연구재료비에 해당",
        )
    )
    narrative: str = "이번 달 특이사항 없음."
    fail_extraction: bool = False

    model: str = "fake-model"
    prompt_version: str = "test-v1"
    extract_calls: int = 0
    suggest_calls: int = 0

    def extract_document(self, *, file_bytes: bytes, mime_type: str) -> ExtractedDoc:
        self.extract_calls += 1
        if self.fail_extraction:
            raise RuntimeError("의도된 추출 실패")
        return self.extraction

    def suggest_category(
        self, *, extraction: ExtractedDoc | None, title: str, vendor_name: str, amount: int
    ) -> CategorySuggestion:
        self.suggest_calls += 1
        return self.suggestion

    def draft_report_narrative(self, *, summary: dict) -> str:
        return self.narrative
