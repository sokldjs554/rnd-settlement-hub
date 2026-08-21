"""AI 미사용(성능 저하) 모드 구현체. ANTHROPIC_API_KEY가 없을 때 사용된다.

모든 호출이 AIUnavailableError를 던지고, 파이프라인은 이를 잡아
룰 검증만으로 계속 진행하며 R-AI-001 플래그로 '수기 대조 필요'를 남긴다.
"""

from app.ai.base import AIClient, AIUnavailableError, CategorySuggestion, ExtractedDoc


class NullAIClient:
    model = "none"
    prompt_version = "none"

    def extract_document(self, *, file_bytes: bytes, mime_type: str) -> ExtractedDoc:
        raise AIUnavailableError("ANTHROPIC_API_KEY가 설정되지 않았습니다.")

    def suggest_category(
        self,
        *,
        extraction: ExtractedDoc | None,
        title: str,
        vendor_name: str,
        amount: int,
        purpose: str | None,
    ) -> CategorySuggestion:
        raise AIUnavailableError("ANTHROPIC_API_KEY가 설정되지 않았습니다.")

    def draft_report_narrative(self, *, summary: dict) -> str:
        raise AIUnavailableError("ANTHROPIC_API_KEY가 설정되지 않았습니다.")


def get_ai_client() -> AIClient:
    """설정에 따라 구현체를 고른다. 실제 Claude 클라이언트는 Phase 6에서 추가."""
    from app.config import get_settings

    if not get_settings().anthropic_api_key:
        return NullAIClient()
    # Phase 6: AnthropicAIClient 반환으로 교체
    from app.ai.anthropic_client import AnthropicAIClient  # noqa: PLC0415

    return AnthropicAIClient()
