from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.models.enums import BudgetCategory, CardMatchStatus, ExpenseStatus


class ReconciliationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    uploaded_by: int
    file_name: str
    total_lines: int
    matched_count: int
    matched_near_count: int
    candidate_count: int
    unmatched_count: int
    created_at: datetime


class ReconciliationLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    row_no: int
    approved_on: date
    merchant_name: str
    merchant_biz_no: str | None
    amount: Decimal
    approval_no: str | None
    card_no_masked: str | None
    match_status: CardMatchStatus
    matched_expense_id: int | None
    note: str | None


class UnmatchedExpenseOut(BaseModel):
    """카드 라인과 대응되지 않은 집행 건 요약 (대사 시점 스냅샷 기준)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    vendor_name: str
    amount: Decimal
    spent_at: date
    category: BudgetCategory
    status: ExpenseStatus


class ReconciliationDetail(ReconciliationOut):
    lines: list[ReconciliationLineOut]
    unmatched_expenses: list[UnmatchedExpenseOut]
