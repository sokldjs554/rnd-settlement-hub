# 프로젝트 규칙

리보틱스 [인턴] AI-Native 풀스택 엔지니어 지원용 포트폴리오 프로젝트.
Claude Code는 매 세션 이 파일을 먼저 읽는다.


## 프로젝트 개요

- **프로젝트명**: R&D 정산 관제 시스템 (가칭)
- **한 줄 설명**: 국가 R&D 과제를 수행하는 스타트업이 RCMS 제출 전 거치는 증빙 수집 → 비목 매칭 → 규정 검증 → 대사 → 정산보고서 과정을 통합한 내부 시스템
- **핵심 업무 문제**: 경영지원 담당자가 엑셀·이메일로 증빙을 모아 눈으로 대사하고 있고, 실수의 비용이 환수·제재로 비대칭적으로 크다
- **핵심 workflow**: 집행 등록 → 증빙 첨부 → AI 구조화·비목 매칭 → 룰+LLM 검증 → 담당자 검토 → 승인 → 보고서 생성 → 대시보드 집계
- **MVP 범위 제한**: 인건비 참여율은 범위 밖 (README 향후 개선사항으로 처리)

## 실행 명령

```bash
# ─ Backend (backend/ 디렉토리에서, .venv 가상환경 사용) ─
# 개발 서버:     uvicorn app.main:app --reload
# 테스트:        pytest            # DATABASE_URL로 settlement_hub_test DB 필요
# 린트:          ruff check . && mypy app
# 마이그레이션:  alembic upgrade head
# 마이그레이션 생성: alembic revision --autogenerate -m "메시지"

# ─ 전체 스택 ─
# Docker:        docker compose up --build   # postgres + api (worker/frontend는 Phase 4/5에서 추가)
```

---

## 배경 — 지원 포지션

리보틱스는 로보틱스와 공간지능 기술을 기반으로 제조공장과 물류센터 등의 산업 현장에서 자율 로봇 지게차 솔루션을 개발한다. 회사는 내부 업무 역시 자동화되어야 한다고 보고 있으며, AI를 적극 활용해 빠르게 문제를 정의하고 개발하고 개선할 수 있는 AI-Native 풀스택 엔지니어를 찾고 있다.

첫 번째 업무는 경영지원 조직의 반복 업무와 정산 업무를 하나의 통합 시스템으로 만드는 것이다.

**업무 범위**: 경영지원 업무의 반복 작업 자동화 / 여러 업무의 데이터를 통합·시각화하는 대시보드 / 외부 API 및 공공데이터 연동 / AI를 활용한 반복 문서 자동 생성 / 이후 RCS, FMS 등 로봇 핵심 시스템 개발로 확장 가능

**자격요건**: React·Next.js / MySQL·PostgreSQL / REST API / AI 도구 활용 / 실제 서비스 개발 경험 / 기획부터 배포까지 수행할 수 있는 능력

## 배경 — 개발자 역량

이미 경험해 본 기술: React, REST API, MySQL / PostgreSQL, Python, AI·LLM 관련 개발, Git / GitHub, Linux.

따라서 "React를 사용했습니다", "REST API를 만들었습니다", "PostgreSQL을 사용했습니다" 수준으로는 부족하다. **이 기술들로 실제 문제를 해결했다는 증거**가 코드에 드러나야 한다.

---

## 1. 프로젝트는 반드시 "하나의 제품"이어야 한다

각 기능을 억지로 붙이지 마라. 다음처럼 되어서는 안 된다.

> React + CRUD + AI Chatbot + API + Dashboard

이런 식의 **기술 전시형 프로젝트는 금지한다.**

대신 하나의 명확한 업무 문제를 중심으로 모든 기능이 연결되어야 한다. 예:

```
업무 데이터 수집 → 외부 데이터 결합 → DB 저장 → 규칙 기반 처리
→ AI 분석 → 담당자 검토 → 자동 문서 생성 → 승인
→ 처리 결과 기록 → 대시보드 집계 → 감사 로그
```

이렇게 하나의 업무 lifecycle을 만들어라.

## 2. Frontend

가능하면 다음을 사용한다.

Next.js / React / TypeScript / TanStack Query / 적절한 UI component system / Chart·data visualization / Form validation / Error handling / Loading state / Empty state

단순 화면이 아니라 **실제 업무 시스템처럼** 만들어라. 예를 들어 검색, 필터, 정렬, 페이지네이션, 상세 페이지, 상태 변경, 승인, 이력 조회, 첨부 데이터, 알림, 통계, audit log 등을 적절하게 포함하라.

## 3. Backend

REST API를 명확하게 설계하라. 가능한 스택: Python / FastAPI / PostgreSQL / SQLAlchemy / Pydantic. 필요한 경우 background job 또는 task queue를 도입하라.

API는 단순 CRUD가 아니라 **실제 업무 workflow를 표현**해야 한다. 예:

```
POST   /requests
GET    /requests
GET    /requests/{id}
PATCH  /requests/{id}
POST   /requests/{id}/approve
POST   /requests/{id}/reject
POST   /requests/{id}/generate-document
GET    /dashboard/summary
```

단, **endpoint 숫자를 늘리기 위한 API는 만들지 마라.**

## 4. Database

PostgreSQL을 기본 DB로 사용하는 방향을 우선 검토한다. 반드시 관계형 데이터 모델을 제대로 설계하라. 단순 테이블 2~3개로 끝내지 말고 실제 서비스의 관계를 표현하라.

필요하다면 고려할 구조: `users`, `organizations`, `requests`, `request_items`, `approvals`, `documents`, `external_data`, `automation_runs`, `audit_logs`, `notifications`

**다만 실제 최종 도메인에 필요한 테이블만 설계하라.**

다음도 반드시 고려한다: Primary Key / Foreign Key / Index / Unique constraint / Enum·status / Transaction / Soft delete / CreatedAt·UpdatedAt / Audit information

## 5. AI는 장식으로 넣지 마라

가장 중요한 조건이다. AI chatbot 하나 붙이고 "AI도 활용했습니다"라고 끝내면 안 된다. **AI가 업무 흐름 안에서 실질적인 역할을 해야 한다.**

```
문서·데이터 입력 → AI 구조화 → 규칙 기반 검증 → AI 판단 보조
→ 담당자 검토 → AI 문서 생성 → 기록
```

AI의 hallucination이나 잘못된 판단 문제도 고려해야 한다. 필요하면 다음을 설계하라.

Structured output / JSON schema / Confidence / Rule-based validation / Human-in-the-loop / Prompt versioning / AI 결과 저장 / **AI 결과와 최종 인간 판단 분리**

## 6. 외부 API 연동

외부 API는 **최소 하나 이상 실제로 사용**하라. 단순 조회용 API는 피하라. 외부 데이터가 실제 업무 의사결정에 영향을 미쳐야 한다.

```
외부 데이터 수집 → 내부 업무 데이터와 결합 → 자동 계산
→ 담당자에게 알림 → 대시보드 반영
```

가능하면 공공데이터·정부 API 또는 실제 사용 가능한 공개 API를 사용한다. API key가 필요한 경우 README에 안전한 환경변수 설정 방법을 제공하라.

## 7. 자동화

이 프로젝트는 "풀스택"과 동시에 **"AI-Native 업무 자동화"**를 보여줘야 한다. 사람이 버튼을 여러 번 누르지 않아도 되는 workflow를 만들어라.

1. 새로운 업무 데이터 입력
2. 외부 API 조회
3. 데이터 검증
4. DB 저장
5. AI 분석
6. 문서 생성
7. 담당자 알림
8. 승인
9. 결과 기록
10. 대시보드 업데이트

## 8. 대시보드

단순 그래프 모음이 아니다. **실제 관리자가 의사결정을 내릴 수 있어야 한다.**

지표 후보: 처리 건수 / 처리 시간 / 자동화율 / 실패율 / 보류 건수 / 승인 대기 / 비용 / 월별 변화 / 업무별 workload / AI 자동 처리 비율

특히 다음 KPI를 고려하라.

- **자동화 전** — 사람이 얼마나 시간이 걸렸는가?
- **자동화 후** — 얼마나 줄어들었는가?

가능하면 프로젝트에 **Before / After 지표**를 넣어라.

## 9. 실제 서비스처럼 만들어라

개발자가 만든 데모가 아니라 실제 스타트업 내부 시스템처럼 만들어라.

Authentication / Authorization / RBAC / Validation / Error handling / Logging / Audit log / Rate limiting / Pagination / Caching / API error response standardization / Environment separation / Secrets management / Database migration / Test / CI/CD

모든 것을 넣을 필요는 없다. 하지만 **실제 서비스에서 중요한 것들을 우선순위에 따라** 설계하라.

## 10. 테스트

테스트를 반드시 포함하라.

- **Backend**: Unit Test / API Test / DB integration test
- **Frontend**: 주요 사용자 시나리오 테스트
- **E2E**: 최소 핵심 workflow 하나 이상

예: 사용자 로그인 → 요청 생성 → AI 처리 → 승인 → 문서 생성 → 완료. 이 전체가 정상적으로 작동하는 테스트를 만들어라.

## 11. Docker / Deployment

로컬에서만 돌아가는 프로젝트를 만들지 마라. 최소한 Docker 기반 실행 환경을 제공하라.

Frontend / Backend / PostgreSQL 을 **Docker Compose로 실행할 수 있게** 만들어라.

가능하다면 실제 클라우드 배포까지 고려한다. 예: Frontend는 Vercel, Backend는 Railway·Render·AWS·GCP, Database는 Neon·Supabase·AWS RDS. 단, 실제 배포 전략은 프로젝트 특성에 맞게 선택한다.

## 12. README에 반드시 포함할 것

GitHub Repository 자체가 포트폴리오가 될 수 있도록 만들어라.

1. 프로젝트 한줄 설명
2. 문제 정의
3. 왜 필요한가
4. 기존 방식의 문제
5. 해결 방법
6. 핵심 기능
7. 시스템 아키텍처
8. 기술 스택
9. 데이터베이스 ERD
10. API 구조
11. AI architecture
12. workflow
13. 실행 방법
14. Docker 실행 방법
15. 환경변수 설정
16. 테스트
17. 배포
18. 성능 / 자동화 효과
19. 한계점
20. 향후 개선사항

## 13. 절대 하지 말아야 할 것

1. 기존 GitHub 프로젝트를 그대로 따라 만들기
2. 튜토리얼 프로젝트를 조금 수정해서 나만의 프로젝트라고 포장하기
3. AI가 모든 코드를 작성하고 내가 이해하지 못하는 구조 만들기
4. 기술을 과도하게 추가해서 복잡하게 만들기
5. 실제 문제보다 기술 스택을 먼저 결정하기
6. AI를 단순 ChatGPT wrapper로 만들기
7. CRUD 화면만 여러 개 만들기
8. README에 과장된 성능 수치 작성하기
9. 실제로 실행되지 않는 기능을 있는 것처럼 작성하기
10. 면접에서 설명하지 못할 기술을 사용하는 것

## 14. 반드시 "3개월 인턴 프로젝트" 수준으로 현실화하라

거대한 스타트업 서비스를 만드는 것이 목적이 아니다. **3개월 동안 개인 개발자가 실제로 완성하고 설명할 수 있는 MVP**를 만드는 것이다.

기능을 무조건 많이 넣지 말고 다음에 집중하라.

- 핵심 문제 1개
- 핵심 workflow 1개
- 핵심 AI 기능 1~2개
- 핵심 자동화
- 핵심 대시보드

그리고 이후에 확장 가능한 architecture를 만들어라.

## 15. 확장 방향

리보틱스라는 점을 고려해 다음 방향으로 자연스럽게 확장될 수 있도록 설계한다.

- Phase 1 — 경영지원 업무 자동화
- Phase 2 — 운영 데이터 통합
- Phase 3 — 실시간 상태 / 이벤트 관리
- Phase 4 — 로봇 운영 데이터와 연계
- Phase 5 — FMS / RCS 등 로봇 시스템과 연결

**단, 억지로 로봇 기능을 넣지 마라.** 처음부터 로봇 관제 프로젝트로 만들지 말고, 일반적인 업무 자동화 문제에서 시작해 자연스럽게 산업 운영 시스템으로 확장되는 구조를 만들어라.

## 16. 면접관 관점 자가검증

구현 중 수시로 다음 질문에 답할 수 있는지 확인하라.

- 이 프로젝트가 왜 필요한가?
- 이 문제를 실제 회사에서 본 적이 있는가?
- 왜 기존 ERP로 해결하지 못하는가?
- 왜 AI가 필요한가?
- AI가 틀리면 어떻게 하는가?
- 데이터는 어떻게 저장하는가?
- API는 어떻게 설계했는가?
- DB transaction은 어떻게 보장하는가?
- 동시 요청이 들어오면 어떻게 되는가?
- 인증 / 권한은 어떻게 관리하는가?
- 시스템 장애가 발생하면 어떻게 되는가?
- 외부 API가 다운되면 어떻게 되는가?
- AI API가 실패하면 어떻게 되는가?
- 작업이 중복 실행되면 어떻게 되는가?
- 이 시스템의 가장 큰 bottleneck은 무엇인가?
- 실제 사용자가 사용한다면 어떤 기능을 가장 먼저 개선할 것인가?

## 17. 개발 원칙

내가 최종적으로 이 프로젝트를 **면접에서 직접 설명해야 한다.** 따라서 코드를 생성할 때마다 반드시 다음을 만족하라.

- 왜 이 구조를 선택했는지 설명할 수 있어야 함
- 과도한 추상화 금지
- 불필요한 디자인 패턴 금지
- 라이브러리를 추가할 경우 이유 설명
- 핵심 비즈니스 로직에는 충분한 주석
- AI 생성 코드라도 이해 가능한 구조
- 명확한 naming
- 타입 안정성
- 에러 처리
