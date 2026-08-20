from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import DbSession, require_role
from app.models import User
from app.models.enums import UserRole
from app.schemas.dashboard import DashboardSummary
from app.services.dashboard import build_dashboard

router = APIRouter(tags=["dashboard"])

ManagerUser = Annotated[User, Depends(require_role(UserRole.MANAGER))]


@router.get("/dashboard/summary", response_model=DashboardSummary)
def dashboard_summary(
    db: DbSession,
    user: ManagerUser,
    project_id: int | None = None,
    months: int = Query(6, ge=1, le=24),
) -> DashboardSummary:
    return build_dashboard(db, project_id, months)
