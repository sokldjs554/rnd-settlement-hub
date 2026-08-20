from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.errors import register_error_handlers
from app.api.router import api_router
from app.db import engine

app = FastAPI(
    title="RnD Settlement Hub API",
    description="국가 R&D 정산 관제 시스템 — RCMS 제출 전 증빙 검증·승인·보고서 워크플로",
    version="0.1.0",
)

# 로컬 개발에서 Next.js(3000) → API(8000) 호출 허용. 운영 origin은 배포 문서에서 다룬다.
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
    """헬스체크. DB 연결까지 확인한다(배포 환경 readiness probe용)."""
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok"}
