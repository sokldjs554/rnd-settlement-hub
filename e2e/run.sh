#!/usr/bin/env bash
# E2E 실행 오케스트레이션:
#   전용 DB(settlement_hub_e2e) 초기화 → 시드 → api·worker·frontend 기동 → playwright test
# 사용:  bash e2e/run.sh            (사전 조건: backend/.venv 설치, frontend 빌드(.next), PG 기동)
set -euo pipefail
cd "$(dirname "$0")"
ROOT=$(cd .. && pwd)

PG_ADMIN_URL="${PG_ADMIN_URL:-postgresql://dev:dev@localhost:5432/postgres}"
export DATABASE_URL="${E2E_DATABASE_URL:-postgresql+psycopg://dev:dev@localhost:5432/settlement_hub_e2e}"
export SECRET_KEY="e2e-secret-key-0123456789abcdef0123456789abcdef"
export UPLOAD_DIR="$(mktemp -d)"
PY="${PYTHON_BIN:-$ROOT/backend/.venv/bin/python}"
BIN="$(dirname "$PY")"

echo "── E2E DB 초기화"
psql "$PG_ADMIN_URL" -tc "SELECT 1 FROM pg_database WHERE datname='settlement_hub_e2e'" | grep -q 1 \
  || psql "$PG_ADMIN_URL" -c "CREATE DATABASE settlement_hub_e2e"
(cd "$ROOT/backend" && "$BIN/alembic" downgrade base && "$BIN/alembic" upgrade head && "$PY" -m app.seed)

kill_services() {
  # npm/next는 자식 프로세스를 남기므로 패턴으로도 정리한다
  # (살아남은 옛 서버가 재빌드된 청크를 못 찾아 404를 내는 문제 방지)
  kill "${API_PID:-}" "${WORKER_PID:-}" "${FE_PID:-}" 2>/dev/null || true
  pkill -f "next-server" 2>/dev/null || true
  pkill -f "next start" 2>/dev/null || true
  pkill -f "uvicorn app.main:app --port 8000" 2>/dev/null || true
  pkill -f "app.worker" 2>/dev/null || true
}
cleanup() {
  echo "── 서비스 종료"
  kill_services
}
trap cleanup EXIT

echo "── 이전 실행 잔여 프로세스 정리"
kill_services
sleep 1

echo "── 서비스 기동 (api:8000, worker, frontend:3000)"
(cd "$ROOT/backend" && "$BIN/uvicorn" app.main:app --port 8000 >"$UPLOAD_DIR/api.log" 2>&1) & API_PID=$!
(cd "$ROOT/backend" && "$PY" -m app.worker >"$UPLOAD_DIR/worker.log" 2>&1) & WORKER_PID=$!
(cd "$ROOT/frontend" && npm start >"$UPLOAD_DIR/frontend.log" 2>&1) & FE_PID=$!

for i in $(seq 1 30); do
  curl -sf http://localhost:8000/health >/dev/null && curl -sf http://localhost:3000/login >/dev/null && break
  sleep 1
  [ "$i" = 30 ] && { echo "서비스 기동 실패"; cat "$UPLOAD_DIR"/*.log; exit 1; }
done

echo "── Playwright 실행"
npx playwright test "$@"
