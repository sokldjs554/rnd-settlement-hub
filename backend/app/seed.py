"""시드 데이터 스크립트.

실행:
  python -m app.seed          # 기본: 계정 3종 + 과제 2개 + 비목 예산 + 2026 공휴일
  python -m app.seed --demo   # + 다양한 상태의 집행 건(면접 5분 데모·스크린샷용)

멱등: 이미 있는 데이터(이메일·과제번호 기준)는 건너뛴다.
계정(공통 비밀번호 demo1234!):
  admin@demo.kr / manager@demo.kr / researcher@demo.kr
"""

import sys
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db import SessionLocal
from app.models import Budget, Evidence, Expense, Holiday, Project, User
from app.models.enums import BudgetCategory, ExpenseStatus, UserRole

DEMO_PASSWORD = "demo1234!"

USERS = [
    ("admin@demo.kr", "김운영", UserRole.ADMIN),
    ("manager@demo.kr", "이경영", UserRole.MANAGER),
    ("researcher@demo.kr", "박연구", UserRole.RESEARCHER),
]

PROJECTS = [
    {
        "code": "P-2026-001",
        "name": "자율 지게차 인지 모듈 고도화",
        "agency": "한국산업기술기획평가원",
        "start_date": date(2026, 1, 1),
        "end_date": date(2026, 12, 31),
        "budgets": {
            BudgetCategory.MATERIAL: 50_000_000,
            BudgetCategory.EQUIPMENT: 80_000_000,
            BudgetCategory.ACTIVITY: 20_000_000,
            BudgetCategory.INDIRECT: 15_000_000,
        },
    },
    {
        "code": "P-2026-002",
        "name": "물류센터 공간지능 SLAM 실증",
        "agency": "정보통신기획평가원",
        "start_date": date(2026, 3, 1),
        "end_date": date(2027, 2, 28),
        "budgets": {
            BudgetCategory.MATERIAL: 30_000_000,
            BudgetCategory.ACTIVITY: 25_000_000,
        },
    },
]

# 2026년 대한민국 공휴일 (KASI API 동기화 전에도 R-DAY-001 룰이 동작하도록 내장)
HOLIDAYS_2026 = [
    (date(2026, 1, 1), "신정"),
    (date(2026, 2, 16), "설날 연휴"),
    (date(2026, 2, 17), "설날"),
    (date(2026, 2, 18), "설날 연휴"),
    (date(2026, 3, 1), "삼일절"),
    (date(2026, 3, 2), "삼일절 대체공휴일"),
    (date(2026, 5, 5), "어린이날"),
    (date(2026, 5, 24), "부처님오신날"),
    (date(2026, 5, 25), "부처님오신날 대체공휴일"),
    (date(2026, 6, 6), "현충일"),
    (date(2026, 8, 15), "광복절"),
    (date(2026, 8, 17), "광복절 대체공휴일"),
    (date(2026, 9, 24), "추석 연휴"),
    (date(2026, 9, 25), "추석"),
    (date(2026, 9, 26), "추석 연휴"),
    (date(2026, 10, 3), "개천절"),
    (date(2026, 10, 5), "개천절 대체공휴일"),
    (date(2026, 10, 9), "한글날"),
    (date(2026, 12, 25), "성탄절"),
]

# 데모 집행 건: (제목, 거래처, 사업자번호, 금액, 집행일, 비목, 상태)
DEMO_EXPENSES = [
    ("시약 및 배양배지 구입", "바이오켐상사", "1234567891", 480_000, date(2026, 2, 10), BudgetCategory.MATERIAL, ExpenseStatus.APPROVED),
    ("LiDAR 센서 모듈 구입", "센서마트", "2208162517", 3_600_000, date(2026, 2, 20), BudgetCategory.MATERIAL, ExpenseStatus.APPROVED),
    ("학회 출장 KTX 왕복", "한국철도공사", "1348172631", 96_000, date(2026, 3, 5), BudgetCategory.ACTIVITY, ExpenseStatus.APPROVED),
    ("3D 프린터 부품 제작", "메이커테크", "1068706394", 1_250_000, date(2026, 3, 12), BudgetCategory.MATERIAL, ExpenseStatus.NEEDS_REVIEW),
    ("전문가 자문 수당", "김전문", None, 500_000, date(2026, 3, 15), BudgetCategory.ACTIVITY, ExpenseStatus.NEEDS_REVIEW),
    ("실험용 지그 가공", "정밀가공", "1208147521", 800_000, date(2026, 3, 18), BudgetCategory.MATERIAL, ExpenseStatus.DRAFT),
]


def seed_base(db: Session) -> None:
    for email, name, role in USERS:
        if db.execute(select(User).where(User.email == email)).scalar_one_or_none() is None:
            db.add(
                User(email=email, name=name, role=role, password_hash=hash_password(DEMO_PASSWORD))
            )
            print(f"  user: {email} ({role.value})")
    for spec in PROJECTS:
        if (
            db.execute(select(Project).where(Project.code == spec["code"])).scalar_one_or_none()
            is None
        ):
            project = Project(
                code=spec["code"],
                name=spec["name"],
                agency=spec["agency"],
                start_date=spec["start_date"],
                end_date=spec["end_date"],
            )
            db.add(project)
            db.flush()
            for category, amount in spec["budgets"].items():
                db.add(Budget(project_id=project.id, category=category, amount=Decimal(amount)))
            print(f"  project: {spec['code']}")
    for holiday_date, name in HOLIDAYS_2026:
        if db.get(Holiday, holiday_date) is None:
            db.add(Holiday(date=holiday_date, name=name, source="SEED"))
    db.commit()


def seed_demo(db: Session) -> None:
    researcher = db.execute(
        select(User).where(User.email == "researcher@demo.kr")
    ).scalar_one()
    project = db.execute(select(Project).where(Project.code == "P-2026-001")).scalar_one()
    existing = db.execute(
        select(Expense).where(Expense.project_id == project.id)
    ).scalar_one_or_none()
    if existing is not None:
        print("  demo expenses: 이미 존재 — 건너뜀")
        return
    for title, vendor, biz_no, amount, spent, category, status in DEMO_EXPENSES:
        expense = Expense(
            project_id=project.id,
            category=category,
            created_by=researcher.id,
            title=title,
            vendor_name=vendor,
            vendor_biz_no=biz_no,
            amount=Decimal(amount),
            spent_at=spent,
            status=status,
        )
        db.add(expense)
        db.flush()
        # 데모용 가짜 증빙 메타 (파일 실체 없음 — 뷰어는 404를 정상 처리한다)
        db.add(
            Evidence(
                expense_id=expense.id,
                file_path=f"{expense.id}/demo.pdf",
                file_name=f"{title[:10]}_증빙.pdf",
                mime_type="application/pdf",
                size_bytes=1024,
                uploaded_by=researcher.id,
            )
        )
    db.commit()
    print(f"  demo expenses: {len(DEMO_EXPENSES)}건")


if __name__ == "__main__":
    with_demo = "--demo" in sys.argv
    print("시드 데이터 적용 중…")
    with SessionLocal() as session:
        seed_base(session)
        if with_demo:
            seed_demo(session)
    print("완료. 로그인: admin@demo.kr / manager@demo.kr / researcher@demo.kr (demo1234!)")
