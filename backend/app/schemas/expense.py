from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import (
    AiRunStatus,
    ApprovalAction,
    BudgetCategory,
    ExpenseStatus,
    ValidationSeverity,
)


class ExpenseCreate(BaseModel):
    project_id: int
    category: BudgetCategory
    title: str = Field(min_length=1, max_length=255)
    vendor_name: str = Field(min_length=1, max_length=255)
    vendor_biz_no: str | None = Field(default=None)
    purpose: str | None = Field(default=None, max_length=500)  # 사용 용도 (비목 판단 근거)
    amount: Decimal = Field(gt=0, decimal_places=0)
    spent_at: date

    @field_validator("vendor_biz_no")
    @classmethod
    def normalize_biz_no(cls, v: str | None) -> str | None:
        """하이픈 등 구분자를 제거해 숫자 10자리로 정규화한다. 형식 위반은 룰 엔진이 FAIL 처리."""
        if v is None or v.strip() == "":
            return None
        return "".join(ch for ch in v if ch.isdigit())


class ExpenseUpdate(BaseModel):
    category: BudgetCategory | None = None
    title: str | None = Field(default=None, min_length=1, max_length=255)
    vendor_name: str | None = Field(default=None, min_length=1, max_length=255)
    vendor_biz_no: str | None = None
    purpose: str | None = Field(default=None, max_length=500)
    amount: Decimal | None = Field(default=None, gt=0, decimal_places=0)
    spent_at: date | None = None

    @field_validator("vendor_biz_no")
    @classmethod
    def normalize_biz_no(cls, v: str | None) -> str | None:
        if v is None or v.strip() == "":
            return None
        return "".join(ch for ch in v if ch.isdigit())


class ExpenseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    category: BudgetCategory
    title: str
    vendor_name: str
    vendor_biz_no: str | None
    purpose: str | None
    amount: Decimal
    spent_at: date
    status: ExpenseStatus
    reject_reason: str | None
    report_id: int | None
    created_by: int
    created_at: datetime
    updated_at: datetime


class ExpenseListItem(ExpenseOut):
    project_code: str
    created_by_name: str
    # 최근 파이프라인의 최고 심각도 (목록에서 리스크를 한눈에 보기 위함)
    worst_severity: ValidationSeverity | None = None


class EvidenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    file_name: str
    mime_type: str
    size_bytes: int
    created_at: datetime


class AiExtractionOut(BaseModel):
    """AI 증빙 구조화 결과 요약 (ai_runs.output_json에서 추출)."""

    status: AiRunStatus
    doc_type: str | None = None
    vendor_name: str | None = None
    biz_no: str | None = None
    total_amount: Decimal | None = None
    issued_at: date | None = None
    confidence: Decimal | None = None
    error: str | None = None


class AiSuggestionOut(BaseModel):
    """AI 비목 매칭 제안 (최종 비목은 항상 사람이 확정한다)."""

    status: AiRunStatus
    category: BudgetCategory | None = None
    confidence: Decimal | None = None
    rationale: str | None = None


class AiSummaryOut(BaseModel):
    extraction: AiExtractionOut | None = None
    category_suggestion: AiSuggestionOut | None = None


class ValidationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rule_code: str
    severity: ValidationSeverity
    message: str
    detail: dict | None


class ActorOut(BaseModel):
    id: int
    name: str


class ApprovalOut(BaseModel):
    action: ApprovalAction
    override: bool
    comment: str | None
    actor: ActorOut
    created_at: datetime


class ExpenseDetail(ExpenseOut):
    project_code: str
    created_by_name: str
    evidences: list[EvidenceOut]
    ai: AiSummaryOut
    validations: list[ValidationOut]
    approvals: list[ApprovalOut]


class ApproveRequest(BaseModel):
    comment: str | None = None
    # FAIL 룰이 있는 건을 승인하려면 override=True + comment 필수
    override: bool = False


class RejectRequest(BaseModel):
    reason: str = Field(min_length=1)


class HistoryEvent(BaseModel):
    """감사 로그·승인·파이프라인 실행을 합친 타임라인 항목."""

    at: datetime
    type: str
    actor: str | None = None
    data: dict | None = None
