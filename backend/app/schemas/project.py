from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import BudgetCategory, ProjectStatus


class BudgetIn(BaseModel):
    category: BudgetCategory
    amount: Decimal = Field(ge=0, decimal_places=0)


class ProjectCreate(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=255)
    agency: str = Field(min_length=1, max_length=255)
    start_date: date
    end_date: date
    budgets: list[BudgetIn] = Field(min_length=1)

    @model_validator(mode="after")
    def check_period_and_budget_dupes(self) -> "ProjectCreate":
        if self.start_date > self.end_date:
            raise ValueError("연구 시작일이 종료일보다 늦을 수 없습니다.")
        categories = [b.category for b in self.budgets]
        if len(categories) != len(set(categories)):
            raise ValueError("비목이 중복되었습니다.")
        return self


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    agency: str | None = Field(default=None, min_length=1, max_length=255)
    start_date: date | None = None
    end_date: date | None = None
    status: ProjectStatus | None = None


class BudgetSummary(BaseModel):
    """비목별 예산 현황. approved(승인 누적)와 remaining은 SQL SUM으로 계산된 값이다."""

    category: BudgetCategory
    budget: Decimal
    approved: Decimal
    remaining: Decimal


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    agency: str
    start_date: date
    end_date: date
    status: ProjectStatus


class ProjectDetail(ProjectOut):
    budgets: list[BudgetSummary]
