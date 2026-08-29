"""도메인 열거형.

PostgreSQL native ENUM으로 저장된다(값 추가 시 마이그레이션에서 ALTER TYPE ... ADD VALUE).
str 상속: API 직렬화 시 값이 그대로 문자열이 되게 한다.
"""

import enum


class UserRole(enum.StrEnum):
    RESEARCHER = "RESEARCHER"  # 연구원: 집행 등록·제출
    MANAGER = "MANAGER"  # 경영지원 담당자: 검토·승인·보고서
    ADMIN = "ADMIN"  # 관리자: MANAGER + 과제·예산·사용자 관리


class ProjectStatus(enum.StrEnum):
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"


class BudgetCategory(enum.StrEnum):
    """연구개발비 비목 (국가연구개발사업 연구개발비 사용기준의 직접비 세목 + 간접비).

    인건비 계열은 스키마에 존재하지만 참여율 관리는 MVP 범위 밖이다(DESIGN.md 참고).
    """

    PERSONNEL = "PERSONNEL"  # 인건비
    STUDENT_PERSONNEL = "STUDENT_PERSONNEL"  # 학생인건비
    EQUIPMENT = "EQUIPMENT"  # 연구시설·장비비
    MATERIAL = "MATERIAL"  # 연구재료비
    ACTIVITY = "ACTIVITY"  # 연구활동비
    ALLOWANCE = "ALLOWANCE"  # 연구수당
    OUTSOURCED_RND = "OUTSOURCED_RND"  # 위탁연구개발비
    INTL_JOINT_RND = "INTL_JOINT_RND"  # 국제공동연구개발비
    INDIRECT = "INDIRECT"  # 간접비


BUDGET_CATEGORY_LABELS: dict[BudgetCategory, str] = {
    BudgetCategory.PERSONNEL: "인건비",
    BudgetCategory.STUDENT_PERSONNEL: "학생인건비",
    BudgetCategory.EQUIPMENT: "연구시설·장비비",
    BudgetCategory.MATERIAL: "연구재료비",
    BudgetCategory.ACTIVITY: "연구활동비",
    BudgetCategory.ALLOWANCE: "연구수당",
    BudgetCategory.OUTSOURCED_RND: "위탁연구개발비",
    BudgetCategory.INTL_JOINT_RND: "국제공동연구개발비",
    BudgetCategory.INDIRECT: "간접비",
}


class ExpenseStatus(enum.StrEnum):
    """집행 건 상태 머신.

    DRAFT → SUBMITTED → VALIDATING → NEEDS_REVIEW → APPROVED | REJECTED
    REJECTED → DRAFT (연구원이 수정 후 재제출)
    APPROVED 건은 보고서 확정 시 report_id가 설정되며 잠긴다.
    전이는 서비스 레이어 한 곳(expense_service)에서만 수행한다.
    """

    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    VALIDATING = "VALIDATING"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class AiRunKind(enum.StrEnum):
    DOC_EXTRACTION = "DOC_EXTRACTION"  # 증빙 구조화 추출
    CATEGORY_SUGGESTION = "CATEGORY_SUGGESTION"  # 비목 매칭 제안
    REPORT_NARRATIVE = "REPORT_NARRATIVE"  # 보고서 서술부 초안


class AiRunStatus(enum.StrEnum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class ValidationSeverity(enum.StrEnum):
    PASS = "PASS"
    INFO = "INFO"
    WARN = "WARN"  # 검토 필요
    FAIL = "FAIL"  # 승인 차단 권고 (담당자 override 가능, 사유 필수)


class VendorStatus(enum.StrEnum):
    """국세청 사업자 상태조회 결과 (b_stt_cd: 01 계속, 02 휴업, 03 폐업)."""

    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    CLOSED = "CLOSED"
    UNREGISTERED = "UNREGISTERED"  # 국세청에 등록되지 않은 번호
    UNVERIFIED = "UNVERIFIED"  # API 장애 등으로 확인 실패


class ApprovalAction(enum.StrEnum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"


class ReportStatus(enum.StrEnum):
    DRAFT = "DRAFT"
    FINAL = "FINAL"


class AutomationKind(enum.StrEnum):
    EXPENSE_PIPELINE = "EXPENSE_PIPELINE"  # 제출 시 검증 파이프라인
    REPORT_GENERATION = "REPORT_GENERATION"  # 보고서 집계+서술 초안 생성


class AutomationStatus(enum.StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class CardMatchStatus(enum.StrEnum):
    """연구비카드 사용내역 대사 결과.

    판정 기준은 services/reconciliation.py의 match_lines()에 있다.
    MATCHED_NEAR와 CANDIDATE는 확정이 아니라 '사람이 볼 후보'다 —
    룰 엔진의 WARN과 같은 태도로, 기계가 단정하지 않고 근거를 남긴다.
    """

    MATCHED = "MATCHED"  # 사업자번호·금액·일자 전부 일치
    MATCHED_NEAR = "MATCHED_NEAR"  # 사업자번호·금액 일치, 승인일-집행일 차이 허용 범위 내
    CANDIDATE = "CANDIDATE"  # 금액·일자만 일치(사업자번호 결측) — 수기 확인 필요
    UNMATCHED = "UNMATCHED"  # 대응하는 집행 건 없음 — 미등록 집행 의심
