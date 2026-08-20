"""대시보드 집계. 모든 지표는 SQL로 계산한다.

'관리자가 의사결정을 내릴 수 있는가'를 기준으로 지표를 골랐다:
- 예산 소진(어느 비목이 위험한가) / 상태 분포(오늘 무엇부터 처리하나)
- 룰 위반 Top(반복되는 실수 유형) / 리드타임(처리가 빨라지고 있나)
- AI 지표(AI를 믿어도 되나) / Before-After(자동화 효과 — 가정은 가정이라고 명시)
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import Integer, case, func, select
from sqlalchemy.orm import Session

from app.models import (
    AiRun,
    Approval,
    AutomationRun,
    Budget,
    Expense,
    ValidationResult,
)
from app.models.enums import (
    BUDGET_CATEGORY_LABELS,
    AiRunKind,
    AiRunStatus,
    ApprovalAction,
    AutomationKind,
    AutomationStatus,
    BudgetCategory,
    ExpenseStatus,
    ValidationSeverity,
)
from app.schemas.dashboard import (
    AiMetrics,
    AutomationEffect,
    BudgetUsage,
    DashboardSummary,
    MonthlyAmount,
    MonthlyLeadTime,
    StatusCount,
    TopRule,
)

# Before/After 비교용 가정치: 담당자가 집행 1건을 수기 검증(비목 확인·규정 대조·
# 휴폐업 조회·엑셀 기록)하는 데 걸리는 시간. README에 산정 근거와 함께 명시한다.
ASSUMED_MANUAL_MINUTES_PER_CASE = 15


def build_dashboard(db: Session, project_id: int | None, months: int) -> DashboardSummary:
    since = datetime.now(UTC) - timedelta(days=30 * months)

    def scoped(stmt):
        if project_id is not None:
            stmt = stmt.where(Expense.project_id == project_id)
        return stmt

    # ── 비목별 예산 vs 승인 집행 (과제 미지정 시 전 과제 합산) ──
    budget_stmt = select(
        Budget.category, func.coalesce(func.sum(Budget.amount), 0)
    ).group_by(Budget.category)
    if project_id is not None:
        budget_stmt = budget_stmt.where(Budget.project_id == project_id)
    budgets: dict[BudgetCategory, Decimal] = {
        category: total for category, total in db.execute(budget_stmt)
    }

    approved_stmt = scoped(
        select(Expense.category, func.coalesce(func.sum(Expense.amount), 0))
        .where(Expense.status == ExpenseStatus.APPROVED, Expense.deleted_at.is_(None))
        .group_by(Expense.category)
    )
    approved: dict[BudgetCategory, Decimal] = {
        category: total for category, total in db.execute(approved_stmt)
    }

    budget_usage = [
        BudgetUsage(
            category=category,
            label=BUDGET_CATEGORY_LABELS[category],
            budget=Decimal(total),
            approved=Decimal(approved.get(category, 0)),
            remaining=Decimal(total) - Decimal(approved.get(category, 0)),
        )
        for category, total in sorted(budgets.items(), key=lambda x: x[0].value)
    ]

    # ── 상태별 건수·금액 ──
    status_rows = db.execute(
        scoped(
            select(Expense.status, func.count(), func.coalesce(func.sum(Expense.amount), 0))
            .where(Expense.deleted_at.is_(None))
            .group_by(Expense.status)
        )
    ).all()
    status_counts = [
        StatusCount(status=status, count=count, amount=Decimal(amount))
        for status, count, amount in status_rows
    ]

    # ── 룰 위반 Top 5 (최근 N개월, WARN 이상) ──
    top_rule_stmt = (
        select(ValidationResult.rule_code, ValidationResult.severity, func.count())
        .join(Expense, ValidationResult.expense_id == Expense.id)
        .where(
            ValidationResult.severity.in_([ValidationSeverity.WARN, ValidationSeverity.FAIL]),
            ValidationResult.created_at >= since,
        )
        .group_by(ValidationResult.rule_code, ValidationResult.severity)
        .order_by(func.count().desc())
        .limit(5)
    )
    top_rules = [
        TopRule(rule_code=code, severity=severity, count=count)
        for code, severity, count in db.execute(scoped(top_rule_stmt)).all()
    ]

    # ── 제출→승인 리드타임 (월별 중앙값, 일 단위) ──
    # 제출 시점은 해당 건의 첫 파이프라인 등록 시각으로 근사한다
    first_run = (
        select(
            AutomationRun.expense_id.label("expense_id"),
            func.min(AutomationRun.created_at).label("submitted_at"),
        )
        .where(AutomationRun.kind == AutomationKind.EXPENSE_PIPELINE)
        .group_by(AutomationRun.expense_id)
        .subquery()
    )
    month_expr = func.to_char(Approval.created_at, "YYYY-MM")
    lead_seconds = func.extract("epoch", Approval.created_at - first_run.c.submitted_at)
    lead_stmt = (
        select(
            month_expr,
            func.percentile_cont(0.5).within_group(lead_seconds),
        )
        .select_from(Approval)
        .join(first_run, Approval.expense_id == first_run.c.expense_id)
        .join(Expense, Approval.expense_id == Expense.id)
        .where(Approval.action == ApprovalAction.APPROVE, Approval.created_at >= since)
        .group_by(month_expr)
        .order_by(month_expr)
    )
    lead_time = [
        MonthlyLeadTime(month=month, median_days=round(float(seconds) / 86400, 2))
        for month, seconds in db.execute(scoped(lead_stmt)).all()
        if seconds is not None
    ]

    # ── 월별 승인 금액 추이 (집행일 기준) ──
    spent_month = func.to_char(Expense.spent_at, "YYYY-MM")
    monthly_rows = db.execute(
        scoped(
            select(spent_month, func.coalesce(func.sum(Expense.amount), 0))
            .where(Expense.status == ExpenseStatus.APPROVED, Expense.deleted_at.is_(None))
            .group_by(spent_month)
            .order_by(spent_month)
        )
    ).all()
    monthly_approved = [
        MonthlyAmount(month=month, approved_amount=Decimal(amount))
        for month, amount in monthly_rows[-months:]
    ]

    # ── AI 지표 ──
    extraction_total, extraction_success = db.execute(
        select(
            func.count(),
            func.coalesce(
                func.sum(case((AiRun.status == AiRunStatus.SUCCESS, 1), else_=0)), 0
            ),
        ).where(AiRun.kind == AiRunKind.DOC_EXTRACTION)
    ).one()

    # 제안 채택률: 각 집행 건의 최근 성공한 비목 제안과 사람이 확정한 비목의 일치 비율
    latest_suggestion = (
        select(AiRun.expense_id, func.max(AiRun.id).label("run_id"))
        .where(AiRun.kind == AiRunKind.CATEGORY_SUGGESTION, AiRun.status == AiRunStatus.SUCCESS)
        .group_by(AiRun.expense_id)
        .subquery()
    )
    suggestion_total, suggestion_adopted = db.execute(
        select(
            func.count(),
            func.coalesce(
                func.sum(
                    case((AiRun.suggested_category == Expense.category, 1), else_=0).cast(
                        Integer
                    )
                ),
                0,
            ),
        )
        .select_from(AiRun)
        .join(latest_suggestion, AiRun.id == latest_suggestion.c.run_id)
        .join(Expense, AiRun.expense_id == Expense.id)
    ).one()

    ai_metrics = AiMetrics(
        extraction_total=extraction_total,
        extraction_success_rate=(
            round(extraction_success / extraction_total, 3) if extraction_total else None
        ),
        suggestion_total=suggestion_total,
        suggestion_adoption_rate=(
            round(suggestion_adopted / suggestion_total, 3) if suggestion_total else None
        ),
    )

    # ── 자동화 효과 (Before: 가정 / After: 실측) ──
    pipeline_seconds = func.extract(
        "epoch", AutomationRun.finished_at - AutomationRun.started_at
    )
    validated_cases, median_seconds = db.execute(
        select(func.count(), func.percentile_cont(0.5).within_group(pipeline_seconds)).where(
            AutomationRun.kind == AutomationKind.EXPENSE_PIPELINE,
            AutomationRun.status == AutomationStatus.SUCCEEDED,
        )
    ).one()

    return DashboardSummary(
        budget_usage=budget_usage,
        status_counts=status_counts,
        top_rules=top_rules,
        lead_time=lead_time,
        monthly_approved=monthly_approved,
        ai_metrics=ai_metrics,
        automation_effect=AutomationEffect(
            assumed_manual_minutes_per_case=ASSUMED_MANUAL_MINUTES_PER_CASE,
            measured_pipeline_seconds_median=(
                round(float(median_seconds), 1) if median_seconds is not None else None
            ),
            validated_cases=validated_cases,
        ),
    )
