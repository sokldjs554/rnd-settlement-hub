#!/bin/sh
# Render 단일 서비스 기동 스크립트.
#
# render.yaml에 명령을 인라인으로 적으면 플랫폼이 문자열을 어떻게 토큰화하는지에
# 동작이 좌우된다(따옴표·괄호·&& 처리 차이로 exit 127). 스크립트로 빼두면
# 셸 해석이 이미지 안에서 일어나므로 그 변수가 사라진다.
#
# 로컬 개발은 docker-compose가 api와 worker를 별도 컨테이너로 띄우므로 이 파일을
# 쓰지 않는다. Render free 플랜이 서비스를 하나만 허용해서 여기서만 둘을 합친다.
#
# 알려진 한계: 워커가 죽어도 API는 계속 응답한다(제출된 건이 검증되지 않은 채 쌓인다).
# 대시보드의 "검토 대기" 건수가 줄지 않으면 워커를 의심할 것. 유료 플랜으로 올려
# 워커를 별도 서비스로 분리하면 플랫폼이 재시작을 책임진다.
set -e

echo "[start] 마이그레이션 적용"
alembic upgrade head

echo "[start] 워커 시작 (백그라운드)"
python -m app.worker &

echo "[start] API 시작 (포트 ${PORT:-8000})"
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
