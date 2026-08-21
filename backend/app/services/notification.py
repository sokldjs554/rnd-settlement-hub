"""인앱 알림 생성 헬퍼 (호출자 트랜잭션에 참여)."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Notification, User
from app.models.enums import UserRole


def notify(db: Session, user_id: int, type_: str, payload: dict[str, Any]) -> None:
    db.add(Notification(user_id=user_id, type=type_, payload=payload))


def notify_managers(db: Session, type_: str, payload: dict[str, Any]) -> None:
    """검토 담당자 전원(MANAGER/ADMIN)에게 알림. 사내 규모에서 팬아웃 비용은 무시 가능."""
    manager_ids = (
        db.execute(
            select(User.id).where(
                User.role.in_([UserRole.MANAGER, UserRole.ADMIN]), User.is_active.is_(True)
            )
        )
        .scalars()
        .all()
    )
    for uid in manager_ids:
        notify(db, uid, type_, payload)
