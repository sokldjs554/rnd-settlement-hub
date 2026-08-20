"""API 공통 의존성: 인증된 사용자, 역할 검사."""

from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.api.errors import AppError
from app.core.security import decode_token
from app.db import get_db
from app.models import User
from app.models.enums import UserRole

# auto_error=False: 토큰이 없을 때 FastAPI 기본 403 대신 표준 envelope 401을 내기 위함
_bearer = HTTPBearer(auto_error=False)

# 역할 계층: 상위 역할은 하위 역할의 권한을 포함한다
_ROLE_LEVEL = {UserRole.RESEARCHER: 1, UserRole.MANAGER: 2, UserRole.ADMIN: 3}


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    if credentials is None:
        raise AppError(401, "UNAUTHORIZED", "로그인이 필요합니다.")
    user_id = decode_token(credentials.credentials, expected_type="access")
    if user_id is None:
        raise AppError(401, "UNAUTHORIZED", "토큰이 유효하지 않거나 만료되었습니다.")
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise AppError(401, "UNAUTHORIZED", "사용 중지된 계정입니다.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
DbSession = Annotated[Session, Depends(get_db)]


def require_role(minimum: UserRole):
    """minimum 이상의 역할을 요구하는 의존성 팩토리. 예: Depends(require_role(UserRole.MANAGER))"""

    def checker(user: CurrentUser) -> User:
        if _ROLE_LEVEL[user.role] < _ROLE_LEVEL[minimum]:
            raise AppError(403, "FORBIDDEN", f"{minimum.value} 이상의 권한이 필요합니다.")
        return user

    return checker
