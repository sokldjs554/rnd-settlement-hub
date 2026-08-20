"""검증 룰 엔진.

설계 원칙:
- 룰은 순수 함수다: 입력(RuleContext) → 출력(RuleResult). DB·네트워크 접근 없음.
  외부 데이터(국세청 조회, AI 추출)는 파이프라인이 미리 조회해 컨텍스트에 담아 전달한다.
  → 룰 단위 테스트가 쉽고, "AI가 판정하는가?"라는 질문에 "아니오, 데이터만 공급한다"로 답할 수 있다.
- 반환 규약: RuleResult(검사 수행됨 — PASS/INFO/WARN/FAIL) 또는 None(전제 데이터가 없어 해당 없음).
- FAIL은 승인 '차단 권고'다. 담당자는 사유를 남기고 override할 수 있다(현실 업무의 예외 인정).
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from app.ai.base import CategorySuggestion, ExtractedDoc
from app.models.enums import BudgetCategory, ValidationSeverity, VendorStatus


@dataclass(frozen=True)
class ExpenseSnapshot:
    """룰 평가에 필요한 집행 건 필드의 불변 스냅샷."""

    id: int
    project_id: int
    category: BudgetCategory
    title: str
    vendor_name: str
    vendor_biz_no: str | None
    amount: Decimal
    spent_at: date


@dataclass(frozen=True)
class RuleContext:
    expense: ExpenseSnapshot
    project_start: date
    project_end: date
    budget_amount: Decimal | None  # 해당 비목 예산 (미등록이면 None)
    approved_amount: Decimal  # 이미 승인된 동일 비목 집행 합
    evidence_count: int
    ai_available: bool  # AI 클라이언트 사용 가능 여부(키 존재)
    extraction: ExtractedDoc | None  # AI 추출 성공 결과
    extraction_failed: bool  # AI 추출을 시도했으나 실패
    suggestion: CategorySuggestion | None
    vendor_status: VendorStatus | None  # 국세청 조회 결과 (조회 대상 아님이면 None)
    duplicate_expense_ids: list[int] = field(default_factory=list)
    nonworking_day: bool | None = None  # 주말·공휴일 여부 (정보 없으면 None)


@dataclass(frozen=True)
class RuleResult:
    rule_code: str
    severity: ValidationSeverity
    message: str
    detail: dict[str, Any] | None = None


def run_all(ctx: RuleContext) -> list[RuleResult]:
    """카탈로그의 모든 룰을 평가한다. None(해당 없음)은 결과에서 제외된다."""
    from app.rules.catalog import ALL_RULES

    return [result for rule in ALL_RULES if (result := rule(ctx)) is not None]
