from fastapi import FastAPI
from sqlalchemy import text

from app.db import engine

app = FastAPI(
    title="RnD Settlement Hub API",
    description="국가 R&D 정산 관제 시스템 — RCMS 제출 전 증빙 검증·승인·보고서 워크플로",
    version="0.1.0",
)


@app.get("/health")
def health() -> dict:
    """헬스체크. DB 연결까지 확인한다(배포 환경 readiness probe용)."""
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok"}
