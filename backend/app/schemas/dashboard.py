from decimal import Decimal

from pydantic import BaseModel

from app.models.enums import BudgetCategory, ExpenseStatus, ValidationSeverity


class BudgetUsage(BaseModel):
    category: BudgetCategory
    label: str
    budget: Decimal
    approved: Decimal
    remaining: Decimal


class StatusCount(BaseModel):
    status: ExpenseStatus
    count: int
    amount: Decimal


class TopRule(BaseModel):
    rule_code: str
    severity: ValidationSeverity
    count: int


class MonthlyLeadTime(BaseModel):
    month: str  # "2026-03"
    median_days: float


class MonthlyAmount(BaseModel):
    month: str
    approved_amount: Decimal


class AiMetrics(BaseModel):
    """AI 품질 지표 — 'AI를 믿어도 되는 수준인가'를 계속 감시한다."""

    extraction_total: int
    extraction_success_rate: float | None  # 호출이 없으면 None
    suggestion_total: int
    suggestion_adoption_rate: float | None  # AI 제안 비목 == 사람 확정 비목 비율


class AutomationEffect(BaseModel):
    """Before/After 지표. 수작업 시간은 '가정'임을 필드명으로 명시한다(과장 금지)."""

    assumed_manual_minutes_per_case: int
    measured_pipeline_seconds_median: float | None
    validated_cases: int


class DashboardSummary(BaseModel):
    budget_usage: list[BudgetUsage]
    status_counts: list[StatusCount]
    top_rules: list[TopRule]
    lead_time: list[MonthlyLeadTime]
    monthly_approved: list[MonthlyAmount]
    ai_metrics: AiMetrics
    automation_effect: AutomationEffect
