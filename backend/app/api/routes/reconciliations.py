from typing import Annotated

from fastapi import APIRouter, Depends, UploadFile
from sqlalchemy import select

from app.api.deps import DbSession, require_role
from app.api.errors import not_found
from app.models import CardReconciliation, Expense, User
from app.models.enums import UserRole
from app.schemas.reconciliation import (
    ReconciliationDetail,
    ReconciliationOut,
    UnmatchedExpenseOut,
)
from app.services import reconciliation as recon_service

router = APIRouter(tags=["reconciliations"])

ManagerUser = Annotated[User, Depends(require_role(UserRole.MANAGER))]


@router.post(
    "/projects/{project_id}/reconciliations", response_model=ReconciliationDetail, status_code=201
)
def upload_statement(
    project_id: int, file: UploadFile, db: DbSession, user: ManagerUser
) -> ReconciliationDetail:
    """카드 사용내역 CSV 업로드 → 즉시 대사 실행, 결과 스냅샷 반환."""
    data = file.file.read(recon_service.MAX_SIZE_BYTES + 1)
    recon = recon_service.run_reconciliation(
        db, project_id, file_name=file.filename or "statement.csv", data=data, user=user
    )
    return _to_detail(db, recon)


@router.get("/reconciliations", response_model=list[ReconciliationOut])
def list_reconciliations(
    db: DbSession, user: ManagerUser, project_id: int | None = None
) -> list[CardReconciliation]:
    stmt = select(CardReconciliation).order_by(CardReconciliation.id.desc())
    if project_id is not None:
        stmt = stmt.where(CardReconciliation.project_id == project_id)
    return list(db.execute(stmt).scalars().all())


@router.get("/reconciliations/{recon_id}", response_model=ReconciliationDetail)
def get_reconciliation(recon_id: int, db: DbSession, user: ManagerUser) -> ReconciliationDetail:
    recon = db.get(CardReconciliation, recon_id)
    if recon is None:
        raise not_found("대사 결과", recon_id)
    return _to_detail(db, recon)


def _to_detail(db: DbSession, recon: CardReconciliation) -> ReconciliationDetail:
    """미대사 집행 건 스냅샷(id 목록)을 현재 집행 건 정보로 풀어 응답을 만든다."""
    ids = recon.unmatched_expense_ids or []
    expenses = (
        list(
            db.execute(
                select(Expense).where(Expense.id.in_(ids)).order_by(Expense.spent_at)
            ).scalars()
        )
        if ids
        else []
    )
    return ReconciliationDetail(
        **ReconciliationOut.model_validate(recon).model_dump(),
        lines=recon.lines,
        unmatched_expenses=[UnmatchedExpenseOut.model_validate(e) for e in expenses],
    )
