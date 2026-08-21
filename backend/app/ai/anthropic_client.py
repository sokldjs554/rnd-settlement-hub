"""Claude API 구현체 (AIClient 프로토콜).

- structured output: client.messages.parse + Pydantic 스키마 → 형식이 보장된 JSON만 받는다
- 증빙 입력: 이미지는 image 블록, PDF는 document 블록 (base64)
- 모델은 AI_MODEL 환경변수로 설정 (기본 claude-opus-5)
- 실패 처리: 여기서는 예외를 그대로 던진다. '실패해도 워크플로를 계속할지'는
  호출자(파이프라인/보고서 서비스)가 결정한다 — 정책과 호출을 분리.
"""

import base64
import logging
from datetime import date
from decimal import Decimal
from typing import Literal

import anthropic
from anthropic.types import DocumentBlockParam, ImageBlockParam
from pydantic import BaseModel, Field

from app.ai.base import CategorySuggestion, ExtractedDoc
from app.ai.prompts import (
    EXTRACTION_SYSTEM,
    EXTRACTION_USER,
    NARRATIVE_SYSTEM,
    PROMPT_VERSION,
    SUGGESTION_SYSTEM,
    narrative_user,
    suggestion_user,
)
from app.config import get_settings
from app.models.enums import BudgetCategory

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 60.0
MAX_RETRIES = 1  # 일시 오류 1회 재시도. 그 이상은 파이프라인 레벨(큐 재시도)의 몫


class ExtractionOutput(BaseModel):
    """증빙 추출 structured output 스키마. 모든 필드는 '못 읽으면 null'이 허용된다."""

    doc_type: Literal["세금계산서", "카드매출전표", "거래명세서", "견적서", "영수증", "기타"] | None
    vendor_name: str | None
    biz_no: str | None = Field(description="하이픈 없는 숫자 10자리")
    total_amount: int | None = Field(description="부가세 포함 합계, 원 단위 정수")
    issued_at: str | None = Field(description="YYYY-MM-DD")
    confidence: float = Field(ge=0, le=1)


class SuggestionOutput(BaseModel):
    category: Literal[
        "PERSONNEL",
        "STUDENT_PERSONNEL",
        "EQUIPMENT",
        "MATERIAL",
        "ACTIVITY",
        "ALLOWANCE",
        "OUTSOURCED_RND",
        "INTL_JOINT_RND",
        "INDIRECT",
    ]
    confidence: float = Field(ge=0, le=1)
    rationale: str


class AnthropicAIClient:
    prompt_version = PROMPT_VERSION

    def __init__(self) -> None:
        settings = get_settings()
        self.model = settings.ai_model
        self._client = anthropic.Anthropic(
            api_key=settings.anthropic_api_key,
            timeout=TIMEOUT_SECONDS,
            max_retries=MAX_RETRIES,
        )

    def extract_document(self, *, file_bytes: bytes, mime_type: str) -> ExtractedDoc:
        data = base64.standard_b64encode(file_bytes).decode()
        file_block: DocumentBlockParam | ImageBlockParam
        if mime_type == "application/pdf":
            file_block = DocumentBlockParam(
                type="document",
                source={"type": "base64", "media_type": "application/pdf", "data": data},
            )
        else:
            # 업로드 화이트리스트(storage.py)와 동일한 형식만 지원한다
            image_media: Literal["image/jpeg", "image/png"] | None = {
                "image/jpeg": "image/jpeg",
                "image/png": "image/png",
            }.get(mime_type)  # type: ignore[assignment]
            if image_media is None:
                raise ValueError(f"지원하지 않는 증빙 형식: {mime_type}")
            file_block = ImageBlockParam(
                type="image",
                source={"type": "base64", "media_type": image_media, "data": data},
            )

        response = self._client.messages.parse(
            model=self.model,
            max_tokens=16000,
            system=EXTRACTION_SYSTEM,
            messages=[
                {
                    "role": "user",
                    "content": [file_block, {"type": "text", "text": EXTRACTION_USER}],
                }
            ],
            output_format=ExtractionOutput,
        )
        output = response.parsed_output
        assert output is not None
        return ExtractedDoc(
            doc_type=output.doc_type,
            vendor_name=output.vendor_name,
            biz_no=_normalize_biz_no(output.biz_no),
            total_amount=output.total_amount,
            issued_at=_parse_date(output.issued_at),
            confidence=Decimal(str(round(output.confidence, 3))),
        )

    def suggest_category(
        self,
        *,
        extraction: ExtractedDoc | None,
        title: str,
        vendor_name: str,
        amount: int,
        purpose: str | None,
    ) -> CategorySuggestion:
        extraction_summary = None
        if extraction is not None:
            extraction_summary = (
                f"문서종류={extraction.doc_type}, 거래처={extraction.vendor_name}, "
                f"금액={extraction.total_amount}"
            )
        response = self._client.messages.parse(
            model=self.model,
            max_tokens=16000,
            system=SUGGESTION_SYSTEM,
            messages=[
                {
                    "role": "user",
                    "content": suggestion_user(
                        title=title,
                        vendor_name=vendor_name,
                        amount=amount,
                        purpose=purpose,
                        extraction_summary=extraction_summary,
                    ),
                }
            ],
            output_format=SuggestionOutput,
        )
        output = response.parsed_output
        assert output is not None
        return CategorySuggestion(
            category=BudgetCategory(output.category),
            confidence=Decimal(str(round(output.confidence, 3))),
            rationale=output.rationale,
        )

    def draft_report_narrative(self, *, summary: dict) -> str:
        import json

        response = self._client.messages.create(
            model=self.model,
            max_tokens=16000,
            system=NARRATIVE_SYSTEM,
            messages=[
                {
                    "role": "user",
                    "content": narrative_user(json.dumps(summary, ensure_ascii=False, indent=2)),
                }
            ],
        )
        text = "".join(block.text for block in response.content if block.type == "text")
        return text.strip()


def _normalize_biz_no(value: str | None) -> str | None:
    if value is None:
        return None
    digits = "".join(ch for ch in value if ch.isdigit())
    return digits if len(digits) == 10 else None


def _parse_date(value: str | None) -> date | None:
    """모델이 형식을 어겨도 파이프라인이 죽지 않게 방어적으로 파싱한다."""
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        logger.warning("AI가 반환한 날짜 형식 무시: %r", value)
        return None
