from datetime import UTC, datetime

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.api.errors import not_found
from app.models import Notification

router = APIRouter(prefix="/notifications", tags=["notifications"])


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    payload: dict
    read_at: datetime | None
    created_at: datetime


@router.get("", response_model=list[NotificationOut])
def list_notifications(
    db: DbSession, user: CurrentUser, unread: bool = False
) -> list[Notification]:
    stmt = (
        select(Notification)
        .where(Notification.user_id == user.id)
        .order_by(Notification.id.desc())
        .limit(50)
    )
    if unread:
        stmt = stmt.where(Notification.read_at.is_(None))
    return list(db.execute(stmt).scalars().all())


@router.patch("/{notification_id}/read", response_model=NotificationOut)
def mark_read(notification_id: int, db: DbSession, user: CurrentUser) -> Notification:
    notification = db.get(Notification, notification_id)
    if notification is None or notification.user_id != user.id:
        raise not_found("알림", notification_id)
    if notification.read_at is None:
        notification.read_at = datetime.now(UTC)
        db.commit()
    return notification
