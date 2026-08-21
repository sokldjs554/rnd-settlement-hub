"""AI 클라이언트 인터페이스.

파이프라인·룰 엔진은 이 인터페이스에만 의존한다. 이렇게 분리한 이유:
- 테스트에서 FakeAIClient로 대체 (실 API 호출 없이 파이프라인 전체를 테스트)
- ANTHROPIC_API_KEY가 없으면 NullAIClient로 성능 저하 모드 동작
- AI 결과는 '데이터 공급'일 뿐, 판정은 룰 엔진과 사람이 한다는 경계를 코드로 표현
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol

from app.models.enums import BudgetCategory


class AIUnavailableError(Exception):
    """AI를 사용할 수 없음(키 없음, API 장애 등). 파이프라인은 이를 잡고 룰 검증만 계속한다."""


@dataclass(frozen=True)
class ExtractedDoc:
    """증빙에서 추출한 구조화 데이터. 모든 필드는 '추출 실패 가능'이므로 Optional이다."""

    doc_type: str | None  # 세금계산서/카드전표/거래명세서/기타
    vendor_name: str | None
    biz_no: str | None  # 숫자 10자리로 정규화된 사업자등록번호
    total_amount: int | None  # 원화 정수
    issued_at: date | None
    confidence: Decimal | None  # 0~1, 추출 전반의 신뢰도


@dataclass(frozen=True)
class CategorySuggestion:
    category: BudgetCategory
    confidence: Decimal
    rationale: str


class AIClient(Protocol):
    """AI 기능 3종. 구현체: AnthropicAIClient(운영), NullAIClient(키 없음), FakeAIClient(테스트)."""

    model: str
    prompt_version: str

    def extract_document(self, *, file_bytes: bytes, mime_type: str) -> ExtractedDoc: ...

    def suggest_category(
        self,
        *,
        extraction: ExtractedDoc | None,
        title: str,
        vendor_name: str,
        amount: int,
        purpose: str | None,
    ) -> CategorySuggestion: ...

    def draft_report_narrative(self, *, summary: dict) -> str: ...
