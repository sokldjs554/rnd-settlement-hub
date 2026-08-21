"""감사 로그 기록 헬퍼.

호출자의 트랜잭션에 참여한다(commit하지 않음) — 본 작업과 로그가 원자적으로 함께 남거나
함께 롤백되게 하기 위함이다.
"""

from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog


def log(
    db: Session,
    *,
    actor_id: int | None,
    entity_type: str,
    entity_id: int,
    action: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuditLog(
            actor_id=actor_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            before=before,
            after=after,
        )
    )
