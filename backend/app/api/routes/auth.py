from fastapi import APIRouter, Request, Response
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.api.errors import AppError
from app.config import get_settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from app.models import User
from app.schemas.auth import LoginRequest, LoginResponse, RefreshResponse, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "refresh_token"


def _set_refresh_cookie(response: Response, token: str) -> None:
    """refresh 토큰은 JS에서 접근 못 하는 httpOnly 쿠키로만 전달한다 (XSS 방어)."""
    response.set_cookie(
        REFRESH_COOKIE,
        token,
        httponly=True,
        samesite="lax",
        secure=False,  # 운영(HTTPS) 배포 시 True — README 배포 섹션에서 다룸
        max_age=get_settings().refresh_token_expire_days * 24 * 3600,
        path="/api/v1/auth",
    )


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, response: Response, db: DbSession) -> LoginResponse:
    user = db.execute(select(User).where(User.email == body.email)).scalar_one_or_none()
    # 계정 존재 여부를 응답으로 구분할 수 없게 동일한 에러를 낸다
    if user is None or not verify_password(body.password, user.password_hash):
        raise AppError(401, "INVALID_CREDENTIALS", "이메일 또는 비밀번호가 올바르지 않습니다.")
    if not user.is_active:
        raise AppError(401, "UNAUTHORIZED", "사용 중지된 계정입니다.")

    _set_refresh_cookie(response, create_refresh_token(user.id))
    return LoginResponse(
        access_token=create_access_token(user.id), user=UserOut.model_validate(user)
    )


@router.post("/refresh", response_model=RefreshResponse)
def refresh(request: Request, response: Response, db: DbSession) -> RefreshResponse:
    token = request.cookies.get(REFRESH_COOKIE)
    user_id = decode_token(token, expected_type="refresh") if token else None
    if user_id is None:
        raise AppError(401, "UNAUTHORIZED", "다시 로그인해 주세요.")
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise AppError(401, "UNAUTHORIZED", "다시 로그인해 주세요.")

    # refresh 토큰도 회전시켜 탈취 시 피해 시간을 줄인다
    _set_refresh_cookie(response, create_refresh_token(user.id))
    return RefreshResponse(access_token=create_access_token(user.id))


@router.post("/logout", status_code=204)
def logout(response: Response) -> None:
    response.delete_cookie(REFRESH_COOKIE, path="/api/v1/auth")


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)
