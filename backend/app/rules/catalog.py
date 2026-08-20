"""검증 룰 카탈로그 (15종).

각 룰의 rationale(어떤 환수/지적 사유를 막는가)은 docs/DESIGN.md §12 참고.
새 룰 추가 방법: 함수를 작성하고 ALL_RULES에 등록하면 끝 — 파이프라인·API 수정 불필요.
"""

from collections.abc import Callable
from datetime import timedelta
from decimal import Decimal

from app.models.enums import ValidationSeverity as S
from app.models.enums import VendorStatus
from app.rules import RuleContext, RuleResult

# AI 추출 신뢰도가 이 값 미만이면 수기 대조를 요구한다
LOW_CONFIDENCE_THRESHOLD = Decimal("0.7")
# 협약 종료 임박 기준
PERIOD_ENDING_SOON_DAYS = 30
# 비목 예산 소진 경고 기준
BUDGET_WARN_RATIO = Decimal("0.8")


def r_evd_001_evidence_required(ctx: RuleContext) -> RuleResult | None:
    """증빙 파일 누락 — 증빙 없는 집행은 정산에서 인정되지 않는다."""
    if ctx.evidence_count == 0:
        return RuleResult("R-EVD-001", S.FAIL, "증빙 파일이 첨부되지 않았습니다.")
    return RuleResult("R-EVD-001", S.PASS, f"증빙 {ctx.evidence_count}건 첨부됨.")


def r_evd_002_amount_match(ctx: RuleContext) -> RuleResult | None:
    """증빙 금액 대사 — AI 추출 금액과 입력 금액이 다르면 장부 불일치."""
    if ctx.extraction is None or ctx.extraction.total_amount is None:
        # 추출 실패는 R-AI-001이 다룬다
        return None
    extracted = Decimal(ctx.extraction.total_amount)
    if extracted != ctx.expense.amount:
        return RuleResult(
            "R-EVD-002",
            S.FAIL,
            "증빙의 금액과 입력한 금액이 일치하지 않습니다.",
            {"extracted": int(extracted), "entered": int(ctx.expense.amount)},
        )
    return RuleResult("R-EVD-002", S.PASS, "증빙 금액과 입력 금액이 일치합니다.")


def r_evd_003_date_match(ctx: RuleContext) -> RuleResult | None:
    """증빙 일자 대사 — 발행일·집행일 불일치는 확인 필요(카드 승인일 차이 등 가능성)."""
    if ctx.extraction is None or ctx.extraction.issued_at is None:
        return None
    if ctx.extraction.issued_at != ctx.expense.spent_at:
        return RuleResult(
            "R-EVD-003",
            S.WARN,
            "증빙의 발행일과 집행일이 다릅니다.",
            {
                "extracted": ctx.extraction.issued_at.isoformat(),
                "entered": ctx.expense.spent_at.isoformat(),
            },
        )
    return RuleResult("R-EVD-003", S.PASS, "증빙 발행일과 집행일이 일치합니다.")


def r_evd_004_biz_no_match(ctx: RuleContext) -> RuleResult | None:
    """증빙 사업자번호 대사 — 다르면 다른 업체의 증빙일 가능성."""
    if ctx.extraction is None or not ctx.extraction.biz_no or not ctx.expense.vendor_biz_no:
        return None
    if ctx.extraction.biz_no != ctx.expense.vendor_biz_no:
        return RuleResult(
            "R-EVD-004",
            S.FAIL,
            "증빙의 사업자등록번호와 입력한 번호가 일치하지 않습니다.",
            {"extracted": ctx.extraction.biz_no, "entered": ctx.expense.vendor_biz_no},
        )
    return RuleResult("R-EVD-004", S.PASS, "증빙 사업자등록번호가 일치합니다.")


def r_prd_001_within_period(ctx: RuleContext) -> RuleResult | None:
    """연구기간 외 집행 — 대표적인 전액 환수 사유."""
    if not (ctx.project_start <= ctx.expense.spent_at <= ctx.project_end):
        return RuleResult(
            "R-PRD-001",
            S.FAIL,
            "연구기간 외 집행입니다.",
            {
                "spent_at": ctx.expense.spent_at.isoformat(),
                "period": f"{ctx.project_start.isoformat()} ~ {ctx.project_end.isoformat()}",
            },
        )
    return RuleResult("R-PRD-001", S.PASS, "연구기간 내 집행입니다.")


def r_prd_002_period_ending_soon(ctx: RuleContext) -> RuleResult | None:
    """협약 종료 임박 집행 — 정산 시 소명 요구가 잦은 구간이라 미리 표시."""
    if (
        ctx.expense.spent_at <= ctx.project_end
        and ctx.expense.spent_at >= ctx.project_end - timedelta(days=PERIOD_ENDING_SOON_DAYS)
    ):
        return RuleResult(
            "R-PRD-002",
            S.INFO,
            f"협약 종료 {PERIOD_ENDING_SOON_DAYS}일 이내의 집행입니다. 소명 자료를 준비해 두세요.",
        )
    return None


def r_bgt_001_budget_available(ctx: RuleContext) -> RuleResult | None:
    """비목 예산 잔액 — 초과 집행은 불인정된다. (승인 시점에 잠금 하에 재검증됨)"""
    if ctx.budget_amount is None:
        return RuleResult(
            "R-BGT-001",
            S.FAIL,
            "해당 비목의 예산이 등록되어 있지 않습니다.",
            {"category": ctx.expense.category.value},
        )
    if ctx.approved_amount + ctx.expense.amount > ctx.budget_amount:
        return RuleResult(
            "R-BGT-001",
            S.FAIL,
            "승인 시 비목 예산을 초과합니다.",
            {
                "budget": int(ctx.budget_amount),
                "approved": int(ctx.approved_amount),
                "amount": int(ctx.expense.amount),
            },
        )
    return RuleResult("R-BGT-001", S.PASS, "비목 예산 잔액이 충분합니다.")


def r_bgt_002_budget_nearly_exhausted(ctx: RuleContext) -> RuleResult | None:
    """비목 예산 80% 초과 소진 경고 — 관리자가 미리 조정할 시간을 준다."""
    if ctx.budget_amount is None or ctx.budget_amount == 0:
        return None
    after = ctx.approved_amount + ctx.expense.amount
    if after <= ctx.budget_amount and after > ctx.budget_amount * BUDGET_WARN_RATIO:
        return RuleResult(
            "R-BGT-002",
            S.WARN,
            "이 건 승인 시 비목 예산의 80%를 초과 소진합니다.",
            {"after_ratio": float(after / ctx.budget_amount)},
        )
    return None


def _valid_biz_no_checksum(biz_no: str) -> bool:
    """사업자등록번호 체크섬(국세청 공식 알고리즘)."""
    if len(biz_no) != 10 or not biz_no.isdigit():
        return False
    digits = [int(c) for c in biz_no]
    weights = [1, 3, 7, 1, 3, 7, 1, 3, 5]
    total = sum(d * w for d, w in zip(digits[:9], weights, strict=True))
    total += (digits[8] * 5) // 10
    return (10 - total % 10) % 10 == digits[9]


def r_vnd_001_biz_no_format(ctx: RuleContext) -> RuleResult | None:
    """사업자등록번호 형식·체크섬 — 오타를 입력 단계에서 잡는다."""
    biz_no = ctx.expense.vendor_biz_no
    if not biz_no:
        return RuleResult("R-VND-001", S.WARN, "사업자등록번호가 입력되지 않았습니다.")
    if not _valid_biz_no_checksum(biz_no):
        return RuleResult(
            "R-VND-001",
            S.FAIL,
            "사업자등록번호 형식이 올바르지 않습니다(체크섬 불일치).",
            {"biz_no": biz_no},
        )
    return RuleResult("R-VND-001", S.PASS, "사업자등록번호 형식이 유효합니다.")


def r_vnd_002_vendor_operating(ctx: RuleContext) -> RuleResult | None:
    """휴폐업 업체 거래 — 국세청 상태조회 기반. 폐업 업체 세금계산서는 매입세액 불공제·환수 사유."""
    status = ctx.vendor_status
    if status is None or status == VendorStatus.UNVERIFIED:
        return None  # 미확인은 R-VND-003이 다룬다
    if status == VendorStatus.CLOSED:
        return RuleResult("R-VND-002", S.FAIL, "폐업한 업체와의 거래입니다.")
    if status == VendorStatus.UNREGISTERED:
        return RuleResult("R-VND-002", S.FAIL, "국세청에 등록되지 않은 사업자등록번호입니다.")
    if status == VendorStatus.SUSPENDED:
        return RuleResult("R-VND-002", S.WARN, "휴업 중인 업체와의 거래입니다.")
    return RuleResult("R-VND-002", S.PASS, "계속사업자(정상 영업 중)입니다.")


def r_vnd_003_vendor_unverified(ctx: RuleContext) -> RuleResult | None:
    """사업자 상태 미확인 — 외부 API 장애 시에도 워크플로는 계속, 대신 수기 확인을 요구."""
    if ctx.vendor_status == VendorStatus.UNVERIFIED:
        return RuleResult(
            "R-VND-003",
            S.WARN,
            "사업자 상태를 확인하지 못했습니다(국세청 API 미응답). 수기 확인이 필요합니다.",
        )
    return None


def r_dup_001_duplicate_suspect(ctx: RuleContext) -> RuleResult | None:
    """중복 집행 의심 — 같은 과제·거래처·금액·일자의 건이 이미 존재."""
    if ctx.duplicate_expense_ids:
        return RuleResult(
            "R-DUP-001",
            S.WARN,
            "동일 거래처·금액·일자의 집행 건이 이미 있습니다. 중복 청구인지 확인하세요.",
            {"expense_ids": ctx.duplicate_expense_ids},
        )
    return RuleResult("R-DUP-001", S.PASS, "중복 의심 건이 없습니다.")


def r_day_001_nonworking_day(ctx: RuleContext) -> RuleResult | None:
    """주말·공휴일 집행 — 정산 시 소명 요구가 잦아 미리 표시한다."""
    if ctx.nonworking_day is True:
        return RuleResult(
            "R-DAY-001",
            S.WARN,
            "주말 또는 공휴일에 집행된 건입니다. 사유를 준비해 두세요.",
            {"spent_at": ctx.expense.spent_at.isoformat()},
        )
    return None


def r_ai_001_extraction_quality(ctx: RuleContext) -> RuleResult | None:
    """AI 추출 상태 — 추출이 없거나 신뢰도가 낮으면 자동 대사를 신뢰하지 말고 수기 대조."""
    if not ctx.ai_available:
        return RuleResult(
            "R-AI-001",
            S.WARN,
            "AI 미사용 모드입니다. 증빙 내용을 수기로 대조해 주세요.",
        )
    if ctx.extraction_failed or (ctx.evidence_count > 0 and ctx.extraction is None):
        return RuleResult(
            "R-AI-001",
            S.WARN,
            "증빙 자동 추출에 실패했습니다. 수기 대조가 필요합니다.",
        )
    if ctx.extraction is not None:
        confidence = ctx.extraction.confidence
        if confidence is not None and confidence < LOW_CONFIDENCE_THRESHOLD:
            return RuleResult(
                "R-AI-001",
                S.WARN,
                "AI 추출 신뢰도가 낮습니다. 수기 대조가 필요합니다.",
                {"confidence": float(confidence), "threshold": float(LOW_CONFIDENCE_THRESHOLD)},
            )
        return RuleResult("R-AI-001", S.PASS, "AI 추출이 정상적으로 수행되었습니다.")
    return None  # 증빙이 없어 추출할 것이 없음 (R-EVD-001이 다룬다)


def r_cat_001_category_mismatch(ctx: RuleContext) -> RuleResult | None:
    """비목 불일치 의심 — AI 제안과 사용자가 선택한 비목이 다르면 검토. 최종 확정은 사람."""
    if ctx.suggestion is None:
        return None
    if ctx.suggestion.category != ctx.expense.category:
        return RuleResult(
            "R-CAT-001",
            S.WARN,
            "AI가 제안한 비목과 선택한 비목이 다릅니다.",
            {
                "suggested": ctx.suggestion.category.value,
                "selected": ctx.expense.category.value,
                "confidence": float(ctx.suggestion.confidence),
                "rationale": ctx.suggestion.rationale,
            },
        )
    return RuleResult(
        "R-CAT-001",
        S.PASS,
        "AI 제안 비목과 선택한 비목이 일치합니다.",
        {"confidence": float(ctx.suggestion.confidence)},
    )


ALL_RULES: list[Callable[[RuleContext], RuleResult | None]] = [
    r_evd_001_evidence_required,
    r_evd_002_amount_match,
    r_evd_003_date_match,
    r_evd_004_biz_no_match,
    r_prd_001_within_period,
    r_prd_002_period_ending_soon,
    r_bgt_001_budget_available,
    r_bgt_002_budget_nearly_exhausted,
    r_vnd_001_biz_no_format,
    r_vnd_002_vendor_operating,
    r_vnd_003_vendor_unverified,
    r_dup_001_duplicate_suspect,
    r_day_001_nonworking_day,
    r_ai_001_extraction_quality,
    r_cat_001_category_mismatch,
]
