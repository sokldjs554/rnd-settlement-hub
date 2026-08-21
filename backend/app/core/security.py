"""비밀번호 해시와 JWT 발급/검증.

- 비밀번호: bcrypt (자동 salt 포함)
- 토큰: HS256 JWT. access(짧은 수명, Authorization 헤더)와
  refresh(긴 수명, httpOnly cookie)를 type 클레임으로 구분한다.
"""

from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.config import get_settings

ALGORITHM = "HS256"


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except ValueError:
        return False


def _create_token(user_id: int, token_type: str, lifetime: timedelta) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "type": token_type,
        "iat": now,
        "exp": now + lifetime,
    }
    return jwt.encode(payload, get_settings().secret_key, algorithm=ALGORITHM)


def create_access_token(user_id: int) -> str:
    minutes = get_settings().access_token_expire_minutes
    return _create_token(user_id, "access", timedelta(minutes=minutes))


def create_refresh_token(user_id: int) -> str:
    days = get_settings().refresh_token_expire_days
    return _create_token(user_id, "refresh", timedelta(days=days))


def decode_token(token: str, expected_type: str) -> int | None:
    """토큰을 검증하고 user_id를 반환한다. 무효/만료/타입 불일치는 None."""
    try:
        payload = jwt.decode(token, get_settings().secret_key, algorithms=[ALGORITHM])
    except jwt.InvalidTokenError:
        return None
    if payload.get("type") != expected_type:
        return None
    try:
        return int(payload["sub"])
    except (KeyError, ValueError):
        return None
