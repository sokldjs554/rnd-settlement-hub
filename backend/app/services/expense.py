"""집행 건 상태 머신과 승인/반려 트랜잭션.

상태 전이는 반드시 이 모듈을 통해서만 일어난다.

DRAFT ──submit──▶ SUBMITTED ──워커──▶ VALIDATING ──완료──▶ NEEDS_REVIEW
                                                            ├─approve─▶ APPROVED
                                                            └─reject──▶ REJECTED ──수정──▶ DRAFT
보고서 FINAL 확정 시 APPROVED 건은 report_id가 설정되고 잠긴다.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.errors import AppError, invalid_transition, not_found
from app.models import Approval, AutomationRun, Expense, User, ValidationResult
from app.models.enums import (
    ApprovalAction,
    ExpenseStatus,
    UserRole,
    ValidationSeverity,
)
from app.services import audit, queue
from app.services.budget import approved_sum, get_budget_for_update
from app.services.notification import notify, notify_managers

EDITABLE_STATUSES = (ExpenseStatus.DRAFT, ExpenseStatus.REJECTED)


def get_expense_or_404(
    db: Session, expense_id: int, *, for_update: bool = False
) -> Expense:
    stmt = select(Expense).where(Expense.id == expense_id, Expense.deleted_at.is_(None))
    if for_update:
        # 상태 전이 전 행 잠금: 동시 submit/approve가 서로의 중간 상태를 못 보게 한다
        stmt = stmt.with_for_update()
    expense = db.execute(stmt).scalar_one_or_none()
    if expense is None:
        raise not_found("집행 건", expense_id)
    return expense


def ensure_can_view(expense: Expense, user: User) -> None:
    """RESEARCHER는 본인 건만 접근 가능하다."""
    if user.role == UserRole.RESEARCHER and expense.created_by != user.id:
        raise not_found("집행 건", expense.id)  # 존재 자체를 노출하지 않는다


def ensure_editable(expense: Expense, user: User) -> None:
    if expense.created_by != user.id and user.role == UserRole.RESEARCHER:
        raise not_found("집행 건", expense.id)
    if expense.report_id is not None:
        raise AppError(409, "EXPENSE_LOCKED", "확정된 보고서에 포함된 건은 수정할 수 없습니다.")
    if expense.status not in EDITABLE_STATUSES:
        raise invalid_transition(expense.status.value, "수정")


def submit(db: Session, expense_id: int, actor: User) -> Expense:
    """제출: DRAFT → SUBMITTED + 검증 파이프라인 큐 등록.

    멱등: 이미 제출되어 파이프라인이 도는 중이면 에러 없이 현재 상태를 반환한다
    (네트워크 재시도로 인한 이중 호출을 사용자 에러로 만들지 않기 위함).
    """
    expense = get_expense_or_404(db, expense_id, for_update=True)
    if expense.created_by != actor.id:
        raise not_found("집행 건", expense_id)

    if expense.status in (ExpenseStatus.SUBMITTED, ExpenseStatus.VALIDATING):
        db.rollback()  # 잠금 해제
        return expense
    if expense.status != ExpenseStatus.DRAFT:
        raise invalid_transition(expense.status.value, "제출")

    expense.status = ExpenseStatus.SUBMITTED
    queue.enqueue_expense_pipeline(db, expense.id)
    audit.log(
        db,
        actor_id=actor.id,
        entity_type="expense",
        entity_id=expense.id,
        action="submit",
        before={"status": "DRAFT"},
        after={"status": "SUBMITTED"},
    )
    db.commit()
    return expense


def latest_run_id(db: Session, expense_id: int) -> int | None:
    return db.execute(
        select(AutomationRun.id)
        .where(AutomationRun.expense_id == expense_id)
        .order_by(AutomationRun.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def latest_validations(db: Session, expense_id: int) -> list[ValidationResult]:
    """가장 최근 파이프라인 실행의 검증 결과 (이전 실행 결과는 이력으로만 남는다)."""
    run_id = latest_run_id(db, expense_id)
    if run_id is None:
        return []
    return list(
        db.execute(
            select(ValidationResult)
            .where(ValidationResult.expense_id == expense_id, ValidationResult.run_id == run_id)
            .order_by(ValidationResult.id)
        )
        .scalars()
        .all()
    )


def approve(
    db: Session, expense_id: int, actor: User, *, comment: str | None, override: bool
) -> Expense:
    """승인: NEEDS_REVIEW → APPROVED.

    동시성 보장(면접 질문 "동시 승인으로 예산이 초과되면?"의 답):
    1) 집행 건 행 잠금 → 같은 건의 이중 승인 차단
    2) 예산 행 잠금(FOR UPDATE) → 같은 비목을 두 건이 동시에 승인할 때
       한 트랜잭션이 잔액 검사~커밋을 끝낼 때까지 다른 쪽이 대기
    3) 잠금을 잡은 뒤 승인 합계를 다시 계산하므로 검사 시점의 잔액이 항상 최신이다
    """
    expense = get_expense_or_404(db, expense_id, for_update=True)
    if expense.status != ExpenseStatus.NEEDS_REVIEW:
        raise invalid_transition(expense.status.value, "승인")

    # FAIL 룰이 있으면 override(사유 필수) 없이는 승인 불가
    fails = [
        v for v in latest_validations(db, expense.id) if v.severity == ValidationSeverity.FAIL
    ]
    if fails and not override:
        raise AppError(
            409,
            "OVERRIDE_REQUIRED",
            "FAIL 판정이 있는 건입니다. 사유를 입력하고 override 승인해 주세요.",
            {"fail_rules": [v.rule_code for v in fails]},
        )
    if override and not (comment and comment.strip()):
        raise AppError(422, "COMMENT_REQUIRED", "override 승인에는 사유가 필요합니다.")

    budget = get_budget_for_update(db, expense.project_id, expense.category)
    if budget is None:
        raise AppError(
            409,
            "BUDGET_NOT_FOUND",
            "해당 비목의 예산이 등록되어 있지 않습니다.",
            {"category": expense.category.value},
        )
    already = approved_sum(db, expense.project_id, expense.category)
    if already + expense.amount > budget.amount:
        raise AppError(
            409,
            "BUDGET_EXCEEDED",
            "승인 시 비목 예산을 초과합니다.",
            {
                "budget": int(budget.amount),
                "approved": int(already),
                "amount": int(expense.amount),
            },
        )

    expense.status = ExpenseStatus.APPROVED
    db.add(
        Approval(
            expense_id=expense.id,
            actor_id=actor.id,
            action=ApprovalAction.APPROVE,
            override=bool(fails and override),
            comment=comment,
        )
    )
    audit.log(
        db,
        actor_id=actor.id,
        entity_type="expense",
        entity_id=expense.id,
        action="approve" if not fails else "approve_override",
        before={"status": "NEEDS_REVIEW"},
        after={"status": "APPROVED", "override": bool(fails and override)},
    )
    notify(
        db,
        expense.created_by,
        "expense_approved",
        {"expense_id": expense.id, "title": expense.title},
    )
    db.commit()
    return expense


def reject(db: Session, expense_id: int, actor: User, *, reason: str) -> Expense:
    """반려: NEEDS_REVIEW → REJECTED (사유 필수). 작성자가 수정하면 DRAFT로 복귀한다."""
    expense = get_expense_or_404(db, expense_id, for_update=True)
    if expense.status != ExpenseStatus.NEEDS_REVIEW:
        raise invalid_transition(expense.status.value, "반려")

    expense.status = ExpenseStatus.REJECTED
    expense.reject_reason = reason
    db.add(
        Approval(
            expense_id=expense.id,
            actor_id=actor.id,
            action=ApprovalAction.REJECT,
            comment=reason,
        )
    )
    audit.log(
        db,
        actor_id=actor.id,
        entity_type="expense",
        entity_id=expense.id,
        action="reject",
        before={"status": "NEEDS_REVIEW"},
        after={"status": "REJECTED", "reason": reason},
    )
    notify(
        db,
        expense.created_by,
        "expense_rejected",
        {"expense_id": expense.id, "title": expense.title, "reason": reason},
    )
    db.commit()
    return expense


def mark_validated(db: Session, expense_id: int) -> None:
    """워커 전용: 파이프라인 완료 시 VALIDATING → NEEDS_REVIEW + 담당자 알림 (commit 없음)."""
    expense = get_expense_or_404(db, expense_id, for_update=True)
    if expense.status != ExpenseStatus.VALIDATING:
        return  # 이미 다른 경로로 상태가 바뀐 경우(경합) 조용히 무시
    expense.status = ExpenseStatus.NEEDS_REVIEW
    audit.log(
        db,
        actor_id=None,
        entity_type="expense",
        entity_id=expense.id,
        action="pipeline_completed",
        before={"status": "VALIDATING"},
        after={"status": "NEEDS_REVIEW"},
    )
    notify_managers(
        db,
        "expense_needs_review",
        {"expense_id": expense.id, "title": expense.title},
    )


def soft_delete(db: Session, expense_id: int, actor: User) -> None:
    expense = get_expense_or_404(db, expense_id, for_update=True)
    if expense.created_by != actor.id and actor.role == UserRole.RESEARCHER:
        raise not_found("집행 건", expense_id)
    if expense.status != ExpenseStatus.DRAFT:
        raise invalid_transition(expense.status.value, "삭제")
    expense.deleted_at = datetime.now(UTC)
    audit.log(
        db,
        actor_id=actor.id,
        entity_type="expense",
        entity_id=expense.id,
        action="delete",
    )
    db.commit()
