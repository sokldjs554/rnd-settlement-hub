from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.api.deps import DbSession, require_role
from app.api.errors import AppError, not_found
from app.models import Report, User
from app.models.enums import ReportStatus, UserRole
from app.schemas.report import ReportCreate, ReportDetail, ReportOut, ReportUpdate
from app.services import audit
from app.services import report as report_service

router = APIRouter(tags=["reports"])

ManagerUser = Annotated[User, Depends(require_role(UserRole.MANAGER))]


@router.post("/projects/{project_id}/reports", response_model=ReportDetail, status_code=201)
def create_report(
    project_id: int, body: ReportCreate, db: DbSession, user: ManagerUser
) -> Report:
    """월별 보고서 생성. 집계(SQL)는 즉시 완성되고, AI 서술 초안은 워커가 비동기로 채운다."""
    return report_service.create_report(db, project_id, body.year, body.month, user)


@router.get("/reports", response_model=list[ReportOut])
def list_reports(
    db: DbSession, user: ManagerUser, project_id: int | None = None
) -> list[Report]:
    stmt = select(Report).order_by(Report.period_year.desc(), Report.period_month.desc())
    if project_id is not None:
        stmt = stmt.where(Report.project_id == project_id)
    return list(db.execute(stmt).scalars().all())


@router.get("/reports/{report_id}", response_model=ReportDetail)
def get_report(report_id: int, db: DbSession, user: ManagerUser) -> Report:
    report = db.get(Report, report_id)
    if report is None:
        raise not_found("보고서", report_id)
    return report


@router.patch("/reports/{report_id}", response_model=ReportDetail)
def update_report(
    report_id: int, body: ReportUpdate, db: DbSession, user: ManagerUser
) -> Report:
    """서술부 수정 — DRAFT 상태에서만. AI 초안을 담당자가 다듬어 확정본을 만든다."""
    report = db.get(Report, report_id)
    if report is None:
        raise not_found("보고서", report_id)
    if report.status != ReportStatus.DRAFT:
        raise AppError(409, "INVALID_STATE_TRANSITION", "확정된 보고서는 수정할 수 없습니다.")
    report.narrative_md = body.narrative_md
    audit.log(
        db,
        actor_id=user.id,
        entity_type="report",
        entity_id=report.id,
        action="update_narrative",
    )
    db.commit()
    return report


@router.post("/reports/{report_id}/finalize", response_model=ReportDetail)
def finalize_report(report_id: int, db: DbSession, user: ManagerUser) -> Report:
    """확정: 숫자 스냅샷 고정 + 기간 내 승인 건들을 이 보고서에 묶어 잠근다."""
    return report_service.finalize(db, report_id, user)
