from datetime import date
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import ColumnElement, case, func, select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, DbSession, require_role
from app.api.errors import AppError, not_found
from app.models import (
    AiRun,
    Approval,
    AuditLog,
    AutomationRun,
    Evidence,
    Expense,
    Project,
    User,
    ValidationResult,
)
from app.models.enums import (
    AiRunKind,
    BudgetCategory,
    ExpenseStatus,
    UserRole,
    ValidationSeverity,
)
from app.schemas.common import Page
from app.schemas.expense import (
    ActorOut,
    AiExtractionOut,
    AiSuggestionOut,
    AiSummaryOut,
    ApprovalOut,
    ApproveRequest,
    EvidenceOut,
    ExpenseCreate,
    ExpenseDetail,
    ExpenseListItem,
    ExpenseOut,
    ExpenseUpdate,
    HistoryEvent,
    RejectRequest,
    ValidationOut,
)
from app.services import audit
from app.services import expense as expense_service
from app.services.storage import evidence_absolute_path, save_evidence_file

router = APIRouter(tags=["expenses"])

ManagerUser = Annotated[User, Depends(require_role(UserRole.MANAGER))]

# 정렬 가능한 컬럼 화이트리스트 (임의 컬럼 정렬 요청 차단)
_SORTABLE = {
    "created_at": Expense.created_at,
    "spent_at": Expense.spent_at,
    "amount": Expense.amount,
    "status": Expense.status,
}


@router.post("/expenses", response_model=ExpenseOut, status_code=201)
def create_expense(body: ExpenseCreate, db: DbSession, user: CurrentUser) -> Expense:
    project = db.get(Project, body.project_id)
    if project is None:
        raise not_found("과제", body.project_id)

    expense = Expense(created_by=user.id, **body.model_dump())
    db.add(expense)
    db.flush()
    audit.log(
        db,
        actor_id=user.id,
        entity_type="expense",
        entity_id=expense.id,
        action="create",
        after={"title": expense.title, "amount": int(expense.amount)},
    )
    db.commit()
    return expense


@router.get("/expenses", response_model=Page[ExpenseListItem])
def list_expenses(
    db: DbSession,
    user: CurrentUser,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    sort: str = Query("-created_at"),
    status: ExpenseStatus | None = None,
    project_id: int | None = None,
    category: BudgetCategory | None = None,
    q: str | None = Query(None, max_length=100),
    spent_from: date | None = None,
    spent_to: date | None = None,
) -> Page[ExpenseListItem]:
    conditions: list[ColumnElement[bool]] = [Expense.deleted_at.is_(None)]
    if user.role == UserRole.RESEARCHER:
        conditions.append(Expense.created_by == user.id)
    if status is not None:
        conditions.append(Expense.status == status)
    if project_id is not None:
        conditions.append(Expense.project_id == project_id)
    if category is not None:
        conditions.append(Expense.category == category)
    if q:
        pattern = f"%{q}%"
        conditions.append(Expense.title.ilike(pattern) | Expense.vendor_name.ilike(pattern))
    if spent_from is not None:
        conditions.append(Expense.spent_at >= spent_from)
    if spent_to is not None:
        conditions.append(Expense.spent_at <= spent_to)

    # 정렬: "-컬럼"은 내림차순
    desc = sort.startswith("-")
    column = _SORTABLE.get(sort.lstrip("-"))
    if column is None:
        raise AppError(422, "VALIDATION_ERROR", "지원하지 않는 정렬 기준입니다.", {"sort": sort})
    order = column.desc() if desc else column.asc()

    total = db.execute(
        select(func.count()).select_from(Expense).where(*conditions)
    ).scalar_one()
    rows = db.execute(
        select(Expense, Project.code, User.name)
        .join(Project, Expense.project_id == Project.id)
        .join(User, Expense.created_by == User.id)
        .where(*conditions)
        .order_by(order, Expense.id.desc())
        .offset((page - 1) * size)
        .limit(size)
    ).all()

    expense_ids = [e.id for e, _, _ in rows]
    worst = _worst_severities(db, expense_ids)
    items = [
        ExpenseListItem(
            **ExpenseOut.model_validate(e).model_dump(),
            project_code=code,
            created_by_name=name,
            worst_severity=worst.get(e.id),
        )
        for e, code, name in rows
    ]
    return Page(items=items, total=total, page=page, size=size)


def _worst_severities(db: Session, expense_ids: list[int]) -> dict[int, ValidationSeverity]:
    """각 집행 건의 '최근 실행' 검증 결과 중 최고 심각도 (목록 리스크 배지용)."""
    if not expense_ids:
        return {}
    latest_run = (
        select(
            AutomationRun.expense_id,
            func.max(AutomationRun.id).label("run_id"),
        )
        .where(AutomationRun.expense_id.in_(expense_ids))
        .group_by(AutomationRun.expense_id)
        .subquery()
    )
    severity_rank = case(
        (ValidationResult.severity == ValidationSeverity.FAIL, 3),
        (ValidationResult.severity == ValidationSeverity.WARN, 2),
        (ValidationResult.severity == ValidationSeverity.INFO, 1),
        else_=0,
    )
    rows = db.execute(
        select(ValidationResult.expense_id, func.max(severity_rank))
        .join(latest_run, ValidationResult.run_id == latest_run.c.run_id)
        .group_by(ValidationResult.expense_id)
    ).all()
    rank_to_severity = {
        3: ValidationSeverity.FAIL,
        2: ValidationSeverity.WARN,
        1: ValidationSeverity.INFO,
        0: ValidationSeverity.PASS,
    }
    return {expense_id: rank_to_severity[rank] for expense_id, rank in rows}


def _ai_summary(db: Session, expense_id: int) -> AiSummaryOut:
    """최근 AI 실행 결과 요약. 출력 JSON은 ai_runs 원문에서 읽는다."""

    def latest(kind: AiRunKind) -> AiRun | None:
        return db.execute(
            select(AiRun)
            .where(AiRun.expense_id == expense_id, AiRun.kind == kind)
            .order_by(AiRun.id.desc())
            .limit(1)
        ).scalar_one_or_none()

    summary = AiSummaryOut()
    if (run := latest(AiRunKind.DOC_EXTRACTION)) is not None:
        output: dict[str, Any] = run.output_json or {}
        summary.extraction = AiExtractionOut(
            status=run.status,
            doc_type=output.get("doc_type"),
            vendor_name=output.get("vendor_name"),
            biz_no=output.get("biz_no"),
            total_amount=(
                Decimal(output["total_amount"]) if output.get("total_amount") is not None else None
            ),
            issued_at=output.get("issued_at"),
            confidence=run.confidence,
            error=run.error,
        )
    if (run := latest(AiRunKind.CATEGORY_SUGGESTION)) is not None:
        output = run.output_json or {}
        summary.category_suggestion = AiSuggestionOut(
            status=run.status,
            category=run.suggested_category,
            confidence=run.confidence,
            rationale=output.get("rationale"),
        )
    return summary


@router.get("/expenses/{expense_id}", response_model=ExpenseDetail)
def get_expense(expense_id: int, db: DbSession, user: CurrentUser) -> ExpenseDetail:
    expense = expense_service.get_expense_or_404(db, expense_id)
    expense_service.ensure_can_view(expense, user)

    project = db.get(Project, expense.project_id)
    creator = db.get(User, expense.created_by)
    assert project is not None and creator is not None  # FK 보장

    approvals = db.execute(
        select(Approval, User.name)
        .join(User, Approval.actor_id == User.id)
        .where(Approval.expense_id == expense.id)
        .order_by(Approval.id)
    ).all()

    return ExpenseDetail(
        **ExpenseOut.model_validate(expense).model_dump(),
        project_code=project.code,
        created_by_name=creator.name,
        evidences=[EvidenceOut.model_validate(e) for e in expense.evidences],
        ai=_ai_summary(db, expense.id),
        validations=[
            ValidationOut.model_validate(v)
            for v in expense_service.latest_validations(db, expense.id)
        ],
        approvals=[
            ApprovalOut(
                action=a.action,
                override=a.override,
                comment=a.comment,
                actor=ActorOut(id=a.actor_id, name=name),
                created_at=a.created_at,
            )
            for a, name in approvals
        ],
    )


@router.patch("/expenses/{expense_id}", response_model=ExpenseOut)
def update_expense(
    expense_id: int, body: ExpenseUpdate, db: DbSession, user: CurrentUser
) -> Expense:
    expense = expense_service.get_expense_or_404(db, expense_id, for_update=True)
    expense_service.ensure_editable(expense, user)

    changes = body.model_dump(exclude_unset=True)
    before = {k: str(getattr(expense, k)) for k in changes}
    for key, value in changes.items():
        setattr(expense, key, value)
    # 반려 건을 수정하면 다시 DRAFT로 (재제출 가능 상태)
    if expense.status == ExpenseStatus.REJECTED:
        before["status"] = "REJECTED"
        expense.status = ExpenseStatus.DRAFT
    audit.log(
        db,
        actor_id=user.id,
        entity_type="expense",
        entity_id=expense.id,
        action="update",
        before=before,
        after={k: str(v) for k, v in changes.items()},
    )
    db.commit()
    return expense


@router.delete("/expenses/{expense_id}", status_code=204)
def delete_expense(expense_id: int, db: DbSession, user: CurrentUser) -> None:
    expense_service.soft_delete(db, expense_id, user)


@router.post("/expenses/{expense_id}/evidences", response_model=EvidenceOut, status_code=201)
def upload_evidence(
    expense_id: int, file: UploadFile, db: DbSession, user: CurrentUser
) -> Evidence:
    expense = expense_service.get_expense_or_404(db, expense_id)
    expense_service.ensure_editable(expense, user)

    relative_path, size = save_evidence_file(file, expense.id)
    evidence = Evidence(
        expense_id=expense.id,
        file_path=relative_path,
        file_name=file.filename or "evidence",
        mime_type=file.content_type or "application/octet-stream",
        size_bytes=size,
        uploaded_by=user.id,
    )
    db.add(evidence)
    db.flush()
    audit.log(
        db,
        actor_id=user.id,
        entity_type="expense",
        entity_id=expense.id,
        action="upload_evidence",
        after={"evidence_id": evidence.id, "file_name": evidence.file_name},
    )
    db.commit()
    return evidence


@router.get("/evidences/{evidence_id}/file")
def download_evidence(evidence_id: int, db: DbSession, user: CurrentUser) -> FileResponse:
    evidence = db.get(Evidence, evidence_id)
    if evidence is None:
        raise not_found("증빙", evidence_id)
    expense = expense_service.get_expense_or_404(db, evidence.expense_id)
    expense_service.ensure_can_view(expense, user)

    path = evidence_absolute_path(evidence.file_path)
    if not path.is_file():
        raise not_found("증빙 파일", evidence_id)
    return FileResponse(path, media_type=evidence.mime_type, filename=evidence.file_name)


@router.post("/expenses/{expense_id}/submit", response_model=ExpenseOut)
def submit_expense(expense_id: int, db: DbSession, user: CurrentUser) -> Expense:
    return expense_service.submit(db, expense_id, user)


@router.post("/expenses/{expense_id}/approve", response_model=ExpenseOut)
def approve_expense(
    expense_id: int, body: ApproveRequest, db: DbSession, user: ManagerUser
) -> Expense:
    return expense_service.approve(
        db, expense_id, user, comment=body.comment, override=body.override
    )


@router.post("/expenses/{expense_id}/reject", response_model=ExpenseOut)
def reject_expense(
    expense_id: int, body: RejectRequest, db: DbSession, user: ManagerUser
) -> Expense:
    return expense_service.reject(db, expense_id, user, reason=body.reason)


@router.get("/expenses/{expense_id}/history", response_model=list[HistoryEvent])
def expense_history(expense_id: int, db: DbSession, user: CurrentUser) -> list[HistoryEvent]:
    """감사 로그 + 승인 이력 + 파이프라인 실행을 시간순 타임라인으로 합친다."""
    expense = expense_service.get_expense_or_404(db, expense_id)
    expense_service.ensure_can_view(expense, user)

    events: list[HistoryEvent] = []

    audit_rows = db.execute(
        select(AuditLog, User.name)
        .outerjoin(User, AuditLog.actor_id == User.id)
        .where(AuditLog.entity_type == "expense", AuditLog.entity_id == expense.id)
    ).all()
    for log_row, actor_name in audit_rows:
        events.append(
            HistoryEvent(
                at=log_row.created_at,
                type=f"audit:{log_row.action}",
                actor=actor_name,
                data={"before": log_row.before, "after": log_row.after},
            )
        )

    runs = (
        db.execute(select(AutomationRun).where(AutomationRun.expense_id == expense.id))
        .scalars()
        .all()
    )
    for run in runs:
        events.append(
            HistoryEvent(
                at=run.created_at,
                type=f"pipeline:{run.status.value.lower()}",
                data={"attempt": run.attempt, "error": run.error},
            )
        )

    # timestamptz 컬럼이라 모두 timezone-aware — 그대로 비교 가능
    events.sort(key=lambda e: e.at, reverse=True)
    return events
