"""표준 에러 응답.

모든 에러는 {"error": {"code", "message", "detail"}} envelope로 통일한다.
프론트엔드가 code로 분기하고 message를 그대로 노출할 수 있게 하기 위함이다.
"""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AppError(Exception):
    """도메인 에러. 서비스 레이어에서 raise하면 핸들러가 envelope로 변환한다."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        detail: dict[str, Any] | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.detail = detail
        super().__init__(message)


# 자주 쓰는 에러의 단축 생성자
def not_found(entity: str, entity_id: int | str) -> AppError:
    return AppError(404, "NOT_FOUND", f"{entity}을(를) 찾을 수 없습니다.", {"id": entity_id})


def forbidden(message: str = "권한이 없습니다.") -> AppError:
    return AppError(403, "FORBIDDEN", message)


def invalid_transition(current: str, action: str) -> AppError:
    return AppError(
        409,
        "INVALID_STATE_TRANSITION",
        f"현재 상태({current})에서는 {action}할 수 없습니다.",
        {"status": current, "action": action},
    )


def _envelope(code: str, message: str, detail: Any = None) -> dict:
    return {"error": {"code": code, "message": message, "detail": detail}}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(exc.code, exc.message, exc.detail),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=_envelope(
                "VALIDATION_ERROR", "요청 형식이 올바르지 않습니다.", jsonable_encoder(exc.errors())
            ),
        )
