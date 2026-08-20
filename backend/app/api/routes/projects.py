from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, DbSession, require_role
from app.api.errors import AppError, not_found
from app.models import Budget, Project, User
from app.models.enums import UserRole
from app.schemas.project import ProjectCreate, ProjectDetail, ProjectOut, ProjectUpdate
from app.services import audit
from app.services.budget import budget_summaries

router = APIRouter(prefix="/projects", tags=["projects"])

AdminUser = Annotated[User, Depends(require_role(UserRole.ADMIN))]


def _get_project_or_404(db: Session, project_id: int) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise not_found("과제", project_id)
    return project


@router.get("", response_model=list[ProjectDetail])
def list_projects(db: DbSession, user: CurrentUser) -> list[ProjectDetail]:
    projects = db.execute(select(Project).order_by(Project.id)).scalars().all()
    return [
        ProjectDetail(
            **ProjectOut.model_validate(p).model_dump(), budgets=budget_summaries(db, p.id)
        )
        for p in projects
    ]


@router.post("", response_model=ProjectDetail, status_code=201)
def create_project(body: ProjectCreate, db: DbSession, user: AdminUser) -> ProjectDetail:
    exists = db.execute(select(Project).where(Project.code == body.code)).scalar_one_or_none()
    if exists is not None:
        raise AppError(409, "DUPLICATE", "이미 등록된 과제번호입니다.", {"code": body.code})

    project = Project(
        code=body.code,
        name=body.name,
        agency=body.agency,
        start_date=body.start_date,
        end_date=body.end_date,
    )
    db.add(project)
    db.flush()  # project.id 확보
    for b in body.budgets:
        db.add(Budget(project_id=project.id, category=b.category, amount=b.amount))
    audit.log(
        db,
        actor_id=user.id,
        entity_type="project",
        entity_id=project.id,
        action="create",
        after={"code": project.code, "budgets": len(body.budgets)},
    )
    db.commit()
    return ProjectDetail(
        **ProjectOut.model_validate(project).model_dump(),
        budgets=budget_summaries(db, project.id),
    )


@router.get("/{project_id}", response_model=ProjectDetail)
def get_project(project_id: int, db: DbSession, user: CurrentUser) -> ProjectDetail:
    project = _get_project_or_404(db, project_id)
    return ProjectDetail(
        **ProjectOut.model_validate(project).model_dump(),
        budgets=budget_summaries(db, project.id),
    )


@router.patch("/{project_id}", response_model=ProjectDetail)
def update_project(
    project_id: int, body: ProjectUpdate, db: DbSession, user: AdminUser
) -> ProjectDetail:
    project = _get_project_or_404(db, project_id)
    changes = body.model_dump(exclude_unset=True)
    before = {k: str(getattr(project, k)) for k in changes}
    for key, value in changes.items():
        setattr(project, key, value)
    if project.start_date > project.end_date:
        raise AppError(422, "UNPROCESSABLE", "연구 시작일이 종료일보다 늦을 수 없습니다.")
    audit.log(
        db,
        actor_id=user.id,
        entity_type="project",
        entity_id=project.id,
        action="update",
        before=before,
        after={k: str(v) for k, v in changes.items()},
    )
    db.commit()
    return ProjectDetail(
        **ProjectOut.model_validate(project).model_dump(),
        budgets=budget_summaries(db, project.id),
    )
