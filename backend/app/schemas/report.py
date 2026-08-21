from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ReportStatus


class ReportCreate(BaseModel):
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)


class ReportUpdate(BaseModel):
    narrative_md: str


class ReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    period_year: int
    period_month: int
    status: ReportStatus
    generated_by: int
    finalized_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ReportDetail(ReportOut):
    # summary_json: SQL 집계 스냅샷 (숫자의 유일한 출처 — AI가 만들지 않는다)
    summary_json: dict | None
    # narrative_md: AI 초안을 담당자가 수정해 확정하는 서술부
    narrative_md: str | None
