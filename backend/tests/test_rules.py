"""룰 엔진 단위 테스트 — 순수 함수이므로 DB 없이 검증한다."""

from datetime import date
from decimal import Decimal

from app.ai.base import CategorySuggestion, ExtractedDoc
from app.models.enums import BudgetCategory, ValidationSeverity, VendorStatus
from app.rules import ExpenseSnapshot, RuleContext, run_all
from app.rules.catalog import _valid_biz_no_checksum

VALID_BIZ_NO = "1234567891"  # 체크섬 유효
INVALID_BIZ_NO = "1234567890"  # 체크섬 무효


def make_ctx(**overrides) -> RuleContext:
    """정상 통과하는 기본 컨텍스트. 테스트마다 필요한 필드만 바꾼다."""
    expense = ExpenseSnapshot(
        id=1,
        project_id=1,
        category=BudgetCategory.MATERIAL,
        title="시약 구입",
        vendor_name="테스트상사",
        vendor_biz_no=VALID_BIZ_NO,
        amount=Decimal(500_000),
        spent_at=date(2026, 3, 10),
    )
    defaults = dict(
        expense=expense,
        project_start=date(2026, 1, 1),
        project_end=date(2026, 12, 31),
        budget_amount=Decimal(10_000_000),
        approved_amount=Decimal(0),
        evidence_count=1,
        ai_available=True,
        extraction=ExtractedDoc(
            doc_type="세금계산서",
            vendor_name="테스트상사",
            biz_no=VALID_BIZ_NO,
            total_amount=500_000,
            issued_at=date(2026, 3, 10),
            confidence=Decimal("0.95"),
        ),
        extraction_failed=False,
        suggestion=CategorySuggestion(
            category=BudgetCategory.MATERIAL, confidence=Decimal("0.9"), rationale="ok"
        ),
        vendor_status=VendorStatus.ACTIVE,
        duplicate_expense_ids=[],
        nonworking_day=False,
    )
    defaults.update(overrides)
    return RuleContext(**defaults)


def result_of(ctx: RuleContext, code: str):
    return next((r for r in run_all(ctx) if r.rule_code == code), None)


def severity_of(ctx: RuleContext, code: str) -> ValidationSeverity | None:
    r = result_of(ctx, code)
    return r.severity if r else None


def replace_expense(**expense_overrides) -> RuleContext:
    """기본 컨텍스트에서 집행 건 필드만 바꾼다."""
    from dataclasses import replace

    return make_ctx(expense=replace(make_ctx().expense, **expense_overrides))


class TestHappyPath:
    def test_all_pass_when_everything_matches(self) -> None:
        results = run_all(make_ctx())
        assert all(r.severity in (ValidationSeverity.PASS,) for r in results), [
            (r.rule_code, r.severity) for r in results
        ]
        # 핵심 룰들이 실제로 평가되었는지 (skip으로 통과한 척하지 않는지)
        codes = {r.rule_code for r in results}
        assert {"R-EVD-001", "R-EVD-002", "R-PRD-001", "R-BGT-001", "R-VND-002"} <= codes


class TestEvidenceRules:
    def test_missing_evidence_fails(self) -> None:
        ctx = make_ctx(evidence_count=0, extraction=None)
        assert severity_of(ctx, "R-EVD-001") == ValidationSeverity.FAIL

    def test_amount_mismatch_fails_with_detail(self) -> None:
        ctx = make_ctx(
            extraction=ExtractedDoc(
                doc_type=None,
                vendor_name=None,
                biz_no=None,
                total_amount=450_000,  # 입력은 500,000
                issued_at=None,
                confidence=Decimal("0.9"),
            )
        )
        r = result_of(ctx, "R-EVD-002")
        assert r is not None and r.severity == ValidationSeverity.FAIL
        assert r.detail == {"extracted": 450000, "entered": 500000}

    def test_date_mismatch_warns(self) -> None:
        ctx = make_ctx(
            extraction=ExtractedDoc(
                doc_type=None,
                vendor_name=None,
                biz_no=None,
                total_amount=500_000,
                issued_at=date(2026, 3, 12),
                confidence=Decimal("0.9"),
            )
        )
        assert severity_of(ctx, "R-EVD-003") == ValidationSeverity.WARN

    def test_biz_no_mismatch_fails(self) -> None:
        ctx = make_ctx(
            extraction=ExtractedDoc(
                doc_type=None,
                vendor_name=None,
                biz_no="9999999999",
                total_amount=500_000,
                issued_at=date(2026, 3, 10),
                confidence=Decimal("0.9"),
            )
        )
        assert severity_of(ctx, "R-EVD-004") == ValidationSeverity.FAIL

    def test_reconciliation_rules_skip_without_extraction(self) -> None:
        """추출이 없으면 대사 룰은 '해당 없음' — 거짓 PASS를 만들지 않는다."""
        ctx = make_ctx(extraction=None, extraction_failed=True)
        assert result_of(ctx, "R-EVD-002") is None
        assert result_of(ctx, "R-EVD-003") is None
        assert result_of(ctx, "R-EVD-004") is None


class TestPeriodRules:
    def test_out_of_period_fails(self) -> None:
        ctx = replace_expense(spent_at=date(2027, 1, 5))
        assert severity_of(ctx, "R-PRD-001") == ValidationSeverity.FAIL

    def test_boundary_dates_pass(self) -> None:
        for boundary in (date(2026, 1, 1), date(2026, 12, 31)):
            ctx = replace_expense(spent_at=boundary)
            assert severity_of(ctx, "R-PRD-001") == ValidationSeverity.PASS

    def test_ending_soon_info(self) -> None:
        ctx = replace_expense(spent_at=date(2026, 12, 15))
        assert severity_of(ctx, "R-PRD-002") == ValidationSeverity.INFO


class TestBudgetRules:
    def test_over_budget_fails(self) -> None:
        ctx = make_ctx(budget_amount=Decimal(1_000_000), approved_amount=Decimal(600_000))
        assert severity_of(ctx, "R-BGT-001") == ValidationSeverity.FAIL

    def test_exactly_full_budget_passes(self) -> None:
        ctx = make_ctx(budget_amount=Decimal(1_000_000), approved_amount=Decimal(500_000))
        assert severity_of(ctx, "R-BGT-001") == ValidationSeverity.PASS

    def test_missing_budget_fails(self) -> None:
        ctx = make_ctx(budget_amount=None)
        assert severity_of(ctx, "R-BGT-001") == ValidationSeverity.FAIL

    def test_nearly_exhausted_warns(self) -> None:
        # 승인 후 90% 소진 (한도 내)
        ctx = make_ctx(budget_amount=Decimal(1_000_000), approved_amount=Decimal(400_000))
        assert severity_of(ctx, "R-BGT-002") == ValidationSeverity.WARN


class TestVendorRules:
    def test_checksum_algorithm(self) -> None:
        assert _valid_biz_no_checksum(VALID_BIZ_NO)
        assert not _valid_biz_no_checksum(INVALID_BIZ_NO)
        assert not _valid_biz_no_checksum("123")
        assert not _valid_biz_no_checksum("abcdefghij")

    def test_invalid_format_fails(self) -> None:
        ctx = replace_expense(vendor_biz_no=INVALID_BIZ_NO)
        assert severity_of(ctx, "R-VND-001") == ValidationSeverity.FAIL

    def test_missing_biz_no_warns(self) -> None:
        ctx = replace_expense(vendor_biz_no=None)
        assert severity_of(ctx, "R-VND-001") == ValidationSeverity.WARN

    def test_closed_vendor_fails(self) -> None:
        ctx = make_ctx(vendor_status=VendorStatus.CLOSED)
        assert severity_of(ctx, "R-VND-002") == ValidationSeverity.FAIL

    def test_suspended_vendor_warns(self) -> None:
        ctx = make_ctx(vendor_status=VendorStatus.SUSPENDED)
        assert severity_of(ctx, "R-VND-002") == ValidationSeverity.WARN

    def test_unverified_vendor_warns_via_vnd_003(self) -> None:
        ctx = make_ctx(vendor_status=VendorStatus.UNVERIFIED)
        assert result_of(ctx, "R-VND-002") is None
        assert severity_of(ctx, "R-VND-003") == ValidationSeverity.WARN


class TestMiscRules:
    def test_duplicates_warn(self) -> None:
        ctx = make_ctx(duplicate_expense_ids=[7, 9])
        r = result_of(ctx, "R-DUP-001")
        assert r is not None and r.severity == ValidationSeverity.WARN
        assert r.detail == {"expense_ids": [7, 9]}

    def test_nonworking_day_warns(self) -> None:
        ctx = make_ctx(nonworking_day=True)
        assert severity_of(ctx, "R-DAY-001") == ValidationSeverity.WARN

    def test_unknown_holiday_info_is_silent(self) -> None:
        ctx = make_ctx(nonworking_day=None)
        assert result_of(ctx, "R-DAY-001") is None


class TestAiRules:
    def test_ai_unavailable_warns(self) -> None:
        ctx = make_ctx(ai_available=False, extraction=None, suggestion=None)
        assert severity_of(ctx, "R-AI-001") == ValidationSeverity.WARN

    def test_extraction_failure_warns(self) -> None:
        ctx = make_ctx(extraction=None, extraction_failed=True)
        assert severity_of(ctx, "R-AI-001") == ValidationSeverity.WARN

    def test_low_confidence_warns(self) -> None:
        ctx = make_ctx(
            extraction=ExtractedDoc(
                doc_type=None,
                vendor_name=None,
                biz_no=VALID_BIZ_NO,
                total_amount=500_000,
                issued_at=date(2026, 3, 10),
                confidence=Decimal("0.5"),
            )
        )
        assert severity_of(ctx, "R-AI-001") == ValidationSeverity.WARN

    def test_category_mismatch_warns_with_rationale(self) -> None:
        ctx = make_ctx(
            suggestion=CategorySuggestion(
                category=BudgetCategory.ACTIVITY,
                confidence=Decimal("0.8"),
                rationale="출장비로 보임",
            )
        )
        r = result_of(ctx, "R-CAT-001")
        assert r is not None and r.severity == ValidationSeverity.WARN
        assert r.detail is not None and r.detail["suggested"] == "ACTIVITY"
