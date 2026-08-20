# 배포 가이드

로컬 전체 실행은 `docker compose up --build` 하나로 끝난다(README 참고).
이 문서는 클라우드 배포(무료 티어 기준) 절차다. 계정 가입·콘솔 조작은 직접 수행해야 한다.

## 구성

| 구성요소 | 서비스 | 설정 파일 |
|---|---|---|
| Frontend | Vercel | `frontend/vercel.json` |
| Backend (API+Worker) | Render | `render.yaml` (Blueprint) |
| Database | Neon (PostgreSQL) | — |

## 1. Neon (DB)

1. https://neon.tech 에서 프로젝트 생성 → 연결 문자열 복사
2. SQLAlchemy 드라이버에 맞게 접두어를 바꾼다:
   `postgresql://...` → `postgresql+psycopg://...` (sslmode 파라미터는 유지)

## 2. Render (Backend)

1. https://render.com → New → **Blueprint** → 이 저장소 선택 (`render.yaml` 자동 인식)
2. 환경변수 입력: `DATABASE_URL`(위 Neon 값), `ANTHROPIC_API_KEY`, `NTS_API_KEY`(선택), `KASI_API_KEY`(선택)
3. 배포되면 시드 1회 실행: Render Shell에서 `python -m app.seed --demo`
4. 헬스체크: `https://<서비스>.onrender.com/health`

**왜 API와 워커가 한 서비스인가** — 증빙 파일이 로컬 디스크에 저장되는 MVP 구조에서
워커가 같은 디스크를 읽어야 하는데 Render disk는 서비스 간 공유가 안 된다.
파일 저장을 S3로 교체하면(`app/services/storage.py`만 수정) 워커를 분리할 수 있다.

## 3. Vercel (Frontend)

1. https://vercel.com → Import → 이 저장소, **Root Directory를 `frontend`로 지정**
2. 환경변수: `NEXT_PUBLIC_API_URL=https://<Render 서비스 URL>`
3. 배포 후 백엔드 CORS에 Vercel 도메인 추가:
   `backend/app/main.py`의 `allow_origins`에 `https://<프로젝트>.vercel.app` 추가 → 커밋·재배포

## 4. 배포 후 점검 체크리스트

- [ ] `/health` 200 (DB 연결 포함)
- [ ] demo 계정 로그인 → 집행 등록 → 제출 → 수 초 내 "검토 대기" 전환 (워커 동작 확인)
- [ ] `ANTHROPIC_API_KEY` 설정 시 상세 화면에 AI 추출값 표시
- [ ] `NTS_API_KEY` 설정 시 휴폐업 검증(R-VND-002) 동작 — 없으면 R-VND-003 WARN이 정상

## 운영 주의사항 (무료 티어 한계)

- Render free는 유휴 시 슬립 → 첫 요청이 느리다 (데모 전에 미리 깨워둘 것)
- refresh 쿠키는 `secure=False`로 개발 기본값이다 — 운영 HTTPS에서는
  `backend/app/api/routes/auth.py`의 `_set_refresh_cookie`에서 `secure=True`,
  cross-site 배포(Vercel↔Render 도메인 상이)라면 `samesite="none"`으로 바꿔야 한다
- 파일(증빙)은 Render disk 1GB에 저장된다 — 장기 운영 시 S3 교체 권장
