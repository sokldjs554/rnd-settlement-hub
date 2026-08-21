FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml ./
COPY app ./app
COPY alembic.ini ./
COPY alembic ./alembic
# AI 추출 정확도 벤치마크 세트 (docker compose exec api python -m app.eval_extraction)
COPY eval ./eval

RUN pip install --no-cache-dir .

EXPOSE 8000

# 마이그레이션은 compose command에서 실행 (컨테이너 시작과 스키마 변경을 분리)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
