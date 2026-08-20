# REST API 명세 (v1)

Base URL: `/api/v1` · 응답은 JSON · 시각은 ISO 8601(UTC) · 금액은 원화 정수(문자열이 아닌 number)

구현 상태 범례: ✅ 구현됨 · 🔜 해당 Phase에서 구현 예정

## 공통 규약

### 인증
- `POST /auth/login` 성공 시 **access token**(JWT, Authorization: Bearer 헤더)과
  **refresh token**(httpOnly cookie)을 발급한다.
- access 만료 시 `POST /auth/refresh`로 재발급. 보호된 엔드포인트는 미인증 시 `401`.

### 권한(RBAC)
| 역할 | 범위 |
|---|---|
| RESEARCHER | 집행 건 등록·제출·본인 건 조회, 반려 건 수정 |
| MANAGER | + 전체 조회, 승인/반려, 보고서 생성·확정 |
| ADMIN | + 과제·예산·사용자 관리 |

권한 부족 시 `403`. 이하 표기: `[역할]` = 최소 요구 역할.

### 에러 응답 (표준 envelope)
```json
{ "error": { "code": "EXPENSE_NOT_EDITABLE", "message": "제출된 집행 건은 수정할 수 없습니다.", "detail": {"status": "NEEDS_REVIEW"} } }
```
| HTTP | 대표 code |
|---|---|
| 400 | `VALIDATION_ERROR` (요청 형식 오류) |
| 401 | `UNAUTHORIZED` |
| 403 | `FORBIDDEN` |
| 404 | `NOT_FOUND` |
| 409 | `INVALID_STATE_TRANSITION`, `BUDGET_EXCEEDED`, `DUPLICATE` |
| 422 | `UNPROCESSABLE` (Pydantic 필드 검증) |

### 페이지네이션·정렬·필터 (목록 공통)
```
GET /expenses?page=1&size=20&sort=-created_at&status=NEEDS_REVIEW&project_id=1&category=MATERIAL&q=시약&spent_from=2026-01-01&spent_to=2026-03-31
```
응답: `{ "items": [...], "total": 132, "page": 1, "size": 20 }`
`sort`: 컬럼명, `-` 접두는 내림차순. `q`: 제목·거래처명 부분 일치.

---

## Auth 🔜 Phase 4

| Method | Path | 설명 |
|---|---|---|
| POST | `/auth/login` | `{email, password}` → `{access_token, user}` + refresh cookie |
| POST | `/auth/refresh` | refresh cookie → 새 access token |
| GET | `/auth/me` | 현재 사용자 `{id, email, name, role}` |

## Projects (과제) 🔜 Phase 4

| Method | Path | 권한 | 설명 |
|---|---|---|---|
| GET | `/projects` | 로그인 | 목록 + 비목별 예산/승인 집행/잔액 요약 |
| POST | `/projects` | ADMIN | 과제 + 비목 예산 일괄 등록 |
| GET | `/projects/{id}` | 로그인 | 상세(budgets 포함) |
| PATCH | `/projects/{id}` | ADMIN | 기간·상태·예산 수정 |

**POST /projects 요청 예시**
```json
{
  "code": "P-2026-001",
  "name": "자율 지게차 인지 모듈 개발",
  "agency": "한국산업기술기획평가원",
  "start_date": "2026-01-01",
  "end_date": "2026-12-31",
  "budgets": [
    {"category": "MATERIAL", "amount": 50000000},
    {"category": "ACTIVITY", "amount": 20000000}
  ]
}
```

## Expenses (집행 건) 🔜 Phase 4

| Method | Path | 권한 | 설명 |
|---|---|---|---|
| POST | `/expenses` | RESEARCHER | 등록(DRAFT). `{project_id, category, title, vendor_name, vendor_biz_no?, amount, spent_at}` |
| GET | `/expenses` | 로그인* | 목록. *RESEARCHER는 본인 건만 |
| GET | `/expenses/{id}` | 소유자/MANAGER | 상세: evidences, ai_runs(추출·제안), validation_results, approvals 타임라인 포함 |
| PATCH | `/expenses/{id}` | 소유자 | DRAFT·REJECTED 상태만 수정 가능. REJECTED 수정 시 DRAFT로 복귀 |
| DELETE | `/expenses/{id}` | 소유자 | soft delete. DRAFT만 |
| POST | `/expenses/{id}/evidences` | 소유자 | multipart 업로드. pdf/jpg/png, 최대 10MB |
| GET | `/evidences/{id}/file` | 소유자/MANAGER | 증빙 파일 서빙 |
| POST | `/expenses/{id}/submit` | 소유자 | DRAFT→SUBMITTED + 파이프라인 큐 등록(멱등: 재호출해도 중복 실행 없음) |
| POST | `/expenses/{id}/approve` | MANAGER | NEEDS_REVIEW→APPROVED. body `{comment?, override?}` — FAIL 룰 존재 시 `override: true`+`comment` 필수. 예산 잔액 잠금 검사, 초과 시 409 `BUDGET_EXCEEDED` |
| POST | `/expenses/{id}/reject` | MANAGER | NEEDS_REVIEW→REJECTED. body `{reason}` 필수 |
| GET | `/expenses/{id}/history` | 소유자/MANAGER | audit_logs + approvals + automation_runs 타임라인 |

**상태 전이 규칙** (그 외 전이는 409 `INVALID_STATE_TRANSITION`)
```
DRAFT ──submit──▶ SUBMITTED ──워커──▶ VALIDATING ──완료──▶ NEEDS_REVIEW ──approve──▶ APPROVED
  ▲                                                            └──reject──▶ REJECTED ──수정──▶ DRAFT
보고서 FINAL 확정 시 APPROVED 건은 report_id 설정 + 잠금(수정·반려 불가)
```

**GET /expenses/{id} 응답 골격**
```json
{
  "id": 42, "project_id": 1, "category": "MATERIAL", "status": "NEEDS_REVIEW",
  "title": "시약 구입", "vendor_name": "테스트상사", "vendor_biz_no": "1234567890",
  "amount": 500000, "spent_at": "2026-03-10",
  "evidences": [{"id": 7, "file_name": "tax_invoice.pdf", "mime_type": "application/pdf"}],
  "ai": {
    "extraction": {"vendor_name": "테스트상사", "biz_no": "1234567890", "total_amount": 500000, "issued_at": "2026-03-10", "confidence": 0.94},
    "category_suggestion": {"category": "MATERIAL", "confidence": 0.88, "rationale": "..."}
  },
  "validations": [
    {"rule_code": "R-VND-002", "severity": "FAIL", "message": "폐업 업체와의 거래입니다", "detail": {"b_stt": "폐업자", "end_dt": "20250131"}}
  ],
  "created_by": {"id": 3, "name": "홍길동"}, "created_at": "2026-03-11T02:11:00Z"
}
```

## Reports (정산보고서) 🔜 Phase 4/6

| Method | Path | 권한 | 설명 |
|---|---|---|---|
| POST | `/projects/{id}/reports` | MANAGER | `{year, month}` 월별 보고서 생성 — 집계(SQL) 즉시 + 서술 초안(AI)은 비동기. 이미 있으면 409 |
| GET | `/reports` | MANAGER | 목록 |
| GET | `/reports/{id}` | MANAGER | 상세: summary_json(비목별 집계) + narrative_md |
| PATCH | `/reports/{id}` | MANAGER | DRAFT 상태에서 narrative_md 수정 |
| POST | `/reports/{id}/finalize` | MANAGER | DRAFT→FINAL. 대상 기간 APPROVED 건들에 report_id 설정 + 잠금 (단일 트랜잭션) |

## Dashboard 🔜 Phase 4/5

| Method | Path | 권한 | 설명 |
|---|---|---|---|
| GET | `/dashboard/summary?project_id=&months=6` | MANAGER | 아래 블록을 한 번에 반환 |

```json
{
  "budget_usage": [{"category": "MATERIAL", "budget": 50000000, "approved": 12300000, "remaining": 37700000}],
  "status_counts": {"NEEDS_REVIEW": {"count": 8, "amount": 4200000}, "...": {}},
  "top_rules": [{"rule_code": "R-EVD-002", "severity": "FAIL", "count": 14}],
  "lead_time_days": [{"month": "2026-03", "median": 1.5}],
  "ai_metrics": {"extraction_success_rate": 0.96, "suggestion_adoption_rate": 0.91},
  "automation_effect": {"assumed_manual_minutes_per_case": 15, "measured_pipeline_seconds_median": 24}
}
```

## Notifications 🔜 Phase 4

| Method | Path | 설명 |
|---|---|---|
| GET | `/notifications?unread=true` | 내 알림 목록 |
| PATCH | `/notifications/{id}/read` | 읽음 처리 |

## 시스템

| Method | Path | 설명 |
|---|---|---|
| GET | `/health` | ✅ DB 연결 포함 헬스체크 (prefix 없음) |
| GET | `/docs` | ✅ OpenAPI(Swagger) 자동 문서 (prefix 없음) |
