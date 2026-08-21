from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.errors import register_error_handlers
from app.api.router import api_router
from app.config import get_settings
from app.db import engine

app = FastAPI(
    title="RnD Settlement Hub API",
    description="국가 R&D 정산 관제 시스템 — RCMS 제출 전 증빙 검증·승인·보고서 워크플로",
    version="0.1.0",
)

# 평상시 브라우저는 프론트엔드와 같은 오리진의 /api/v1으로만 호출하고 Next.js가 여기로
# 프록시하므로 CORS가 필요 없다. 아래 설정은 프록시를 우회해 API를 직접 호출하는
# 개발 상황(로컬 3000 → 8000 직접 호출, Swagger 시험)을 위한 것이다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,  # refresh httpOnly cookie 전송에 필요
    allow_methods=["*"],
    allow_headers=["*"],
)

register_error_handlers(app)
app.include_router(api_router)


@app.get("/health")
def health() -> dict:
    """헬스체크 (배포 환경 readiness probe용).

    DB 연결과 함께 선택적 외부 연동의 '설정 여부'를 함께 보고한다.
    키 값 자체는 절대 노출하지 않고 불리언만 반환한다 — 배포 후
    "왜 AI 추출이 안 뜨지?"를 집행 건을 제출해 보지 않고 바로 확인하기 위한 것이다.
    """
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    settings = get_settings()
    return {
        "status": "ok",
        "integrations": {
            "ai": bool(settings.anthropic_api_key),  # False면 룰 검증만 수행(성능 저하 모드)
            "nts": bool(settings.nts_api_key),  # False면 사업자 상태 미확인(R-VND-003)
            "kasi": bool(settings.kasi_api_key),  # False면 내장 공휴일 시드 사용
        },
    }
