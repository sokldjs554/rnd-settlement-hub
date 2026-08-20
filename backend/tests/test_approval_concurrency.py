"""승인 동시성 통합 테스트.

"동시 요청이 들어오면 예산이 초과될 수 있는가?"에 대한 실증:
예산 1,000,000 / 각 700,000짜리 두 건을 두 스레드가 동시에 승인하면,
예산 행 잠금(FOR UPDATE) 덕분에 정확히 한 건만 승인되어야 한다.
"""

import threading

from sqlalchemy.orm import Session

from app.api.errors import AppError
from app.db import SessionLocal
from app.models import Expense
from app.models.enums import ExpenseStatus, UserRole
from app.services import expense as expense_service
from tests.factories import make_budget, make_expense, make_project, make_user


def test_concurrent_approvals_cannot_exceed_budget(db: Session) -> None:
    project = make_project(db)
    make_budget(db, project, amount=1_000_000)
    researcher = make_user(db, email="r@corp.kr")
    manager = make_user(db, email="m@corp.kr", role=UserRole.MANAGER)
    e1 = make_expense(db, project, researcher, amount=700_000)
    e2 = make_expense(db, project, researcher, amount=700_000)
    e1.status = ExpenseStatus.NEEDS_REVIEW
    e2.status = ExpenseStatus.NEEDS_REVIEW
    db.commit()
    expense_ids = [e1.id, e2.id]
    manager_id = manager.id

    barrier = threading.Barrier(2)
    outcomes: dict[int, str] = {}

    def approve_in_thread(expense_id: int) -> None:
        session = SessionLocal()
        try:
            actor = session.get(type(manager), manager_id)
            assert actor is not None
            barrier.wait()  # 두 스레드가 정확히 동시에 승인 시도
            expense_service.approve(session, expense_id, actor, comment=None, override=False)
            outcomes[expense_id] = "APPROVED"
        except AppError as exc:
            outcomes[expense_id] = exc.code
        finally:
            session.close()

    threads = [threading.Thread(target=approve_in_thread, args=(eid,)) for eid in expense_ids]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)

    assert sorted(outcomes.values()) == ["APPROVED", "BUDGET_EXCEEDED"], outcomes

    # DB 기준으로도 승인 합계가 예산을 넘지 않는다
    # (identity map의 스테일 객체가 아니라 스레드들이 커밋한 최신 상태를 읽는다)
    db.expire_all()
    approved = [
        e
        for e in db.query(Expense).all()
        if e.status == ExpenseStatus.APPROVED
    ]
    assert len(approved) == 1
