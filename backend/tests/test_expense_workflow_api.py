"""집행 건 워크플로 API 테스트: 등록 → 증빙 → 제출 → 검토 → 승인/반려."""

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AutomationRun, Expense, Notification, ValidationResult
from app.models.enums import ExpenseStatus, UserRole, ValidationSeverity
from tests.conftest import create_account, login_headers
from tests.factories import make_budget, make_project, make_user

FAKE_PDF = b"%PDF-1.4 fake"


def _setup(client: TestClient, db: Session) -> dict:
    """공통 준비물: 과제+예산, 연구원/담당자 계정과 헤더."""
    project = make_project(db)
    make_budget(db, project, amount=1_000_000)
    db.commit()
    create_account(db, email="r1@corp.kr", role=UserRole.RESEARCHER)
    create_account(db, email="m1@corp.kr", role=UserRole.MANAGER)
    return {
        "project_id": project.id,
        "researcher": login_headers(client, "r1@corp.kr"),
        "manager": login_headers(client, "m1@corp.kr"),
    }


def _create_expense(client: TestClient, ctx: dict, *, amount: int = 500_000) -> int:
    res = client.post(
        "/api/v1/expenses",
        headers=ctx["researcher"],
        json={
            "project_id": ctx["project_id"],
            "category": "MATERIAL",
            "title": "시약 구입",
            "vendor_name": "테스트상사",
            "vendor_biz_no": "123-45-67890",
            "amount": amount,
            "spent_at": "2026-03-10",
        },
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _force_status(db: Session, expense_id: int, status: ExpenseStatus) -> None:
    """파이프라인(워커)이 만들 상태를 테스트에서 직접 만든다."""
    expense = db.get(Expense, expense_id)
    assert expense is not None
    expense.status = status
    db.commit()


def test_create_normalizes_biz_no_and_starts_draft(client: TestClient, db: Session) -> None:
    ctx = _setup(client, db)
    expense_id = _create_expense(client, ctx)

    res = client.get(f"/api/v1/expenses/{expense_id}", headers=ctx["researcher"])
    body = res.json()
    assert body["status"] == "DRAFT"
    assert body["vendor_biz_no"] == "1234567890"  # 하이픈 제거 정규화


def test_researcher_sees_only_own_expenses(client: TestClient, db: Session) -> None:
    ctx = _setup(client, db)
    _create_expense(client, ctx)
    other = make_user(db, email="r2@corp.kr")
    db.commit()
    create_account(db, email="r3@corp.kr", role=UserRole.RESEARCHER)
    assert other  # 다른 연구원 존재

    res = client.get("/api/v1/expenses", headers=login_headers(client, "r3@corp.kr"))
    assert res.status_code == 200
    assert res.json()["total"] == 0

    # 담당자는 전체가 보인다
    res = client.get("/api/v1/expenses", headers=ctx["manager"])
    assert res.json()["total"] == 1


def test_evidence_upload_and_mime_whitelist(client: TestClient, db: Session) -> None:
    ctx = _setup(client, db)
    expense_id = _create_expense(client, ctx)

    ok = client.post(
        f"/api/v1/expenses/{expense_id}/evidences",
        headers=ctx["researcher"],
        files={"file": ("tax_invoice.pdf", FAKE_PDF, "application/pdf")},
    )
    assert ok.status_code == 201
    assert ok.json()["file_name"] == "tax_invoice.pdf"

    bad = client.post(
        f"/api/v1/expenses/{expense_id}/evidences",
        headers=ctx["researcher"],
        files={"file": ("virus.exe", b"MZ", "application/x-msdownload")},
    )
    assert bad.status_code == 422
    assert bad.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"

    # 업로드한 파일을 다시 내려받을 수 있다
    evidence_id = ok.json()["id"]
    download = client.get(f"/api/v1/evidences/{evidence_id}/file", headers=ctx["manager"])
    assert download.status_code == 200
    assert download.content == FAKE_PDF


def test_submit_enqueues_pipeline_and_is_idempotent(client: TestClient, db: Session) -> None:
    ctx = _setup(client, db)
    expense_id = _create_expense(client, ctx)

    first = client.post(f"/api/v1/expenses/{expense_id}/submit", headers=ctx["researcher"])
    assert first.status_code == 200
    assert first.json()["status"] == "SUBMITTED"

    # 재호출해도 에러가 아니고 작업이 중복 등록되지 않는다
    second = client.post(f"/api/v1/expenses/{expense_id}/submit", headers=ctx["researcher"])
    assert second.status_code == 200

    runs = db.execute(
        select(AutomationRun).where(AutomationRun.expense_id == expense_id)
    ).scalars().all()
    assert len(runs) == 1


def test_approve_happy_path(client: TestClient, db: Session) -> None:
    ctx = _setup(client, db)
    expense_id = _create_expense(client, ctx)
    _force_status(db, expense_id, ExpenseStatus.NEEDS_REVIEW)

    res = client.post(
        f"/api/v1/expenses/{expense_id}/approve", headers=ctx["manager"], json={}
    )
    assert res.status_code == 200
    assert res.json()["status"] == "APPROVED"

    # 승인 시 작성자에게 알림이 남는다
    notes = db.execute(select(Notification)).scalars().all()
    assert any(n.type == "expense_approved" for n in notes)


def test_approve_rejected_when_budget_exceeded(client: TestClient, db: Session) -> None:
    ctx = _setup(client, db)  # MATERIAL 예산 1,000,000
    first = _create_expense(client, ctx, amount=700_000)
    second = _create_expense(client, ctx, amount=700_000)
    _force_status(db, first, ExpenseStatus.NEEDS_REVIEW)
    _force_status(db, second, ExpenseStatus.NEEDS_REVIEW)

    assert (
        client.post(f"/api/v1/expenses/{first}/approve", headers=ctx["manager"], json={})
        .status_code
        == 200
    )
    res = client.post(f"/api/v1/expenses/{second}/approve", headers=ctx["manager"], json={})
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "BUDGET_EXCEEDED"


def test_approve_with_fail_rule_requires_override(client: TestClient, db: Session) -> None:
    ctx = _setup(client, db)
    expense_id = _create_expense(client, ctx)

    # 파이프라인이 남긴 FAIL 검증 결과를 재현
    run = AutomationRun(
        kind="EXPENSE_PIPELINE",
        expense_id=expense_id,
        idempotency_key=f"expense:{expense_id}:pipeline:1",
    )
    db.add(run)
    db.flush()
    db.add(
        ValidationResult(
            expense_id=expense_id,
            run_id=run.id,
            rule_code="R-VND-002",
            severity=ValidationSeverity.FAIL,
            message="폐업 업체와의 거래입니다",
        )
    )
    db.commit()
    _force_status(db, expense_id, ExpenseStatus.NEEDS_REVIEW)

    plain = client.post(
        f"/api/v1/expenses/{expense_id}/approve", headers=ctx["manager"], json={}
    )
    assert plain.status_code == 409
    assert plain.json()["error"]["code"] == "OVERRIDE_REQUIRED"

    no_comment = client.post(
        f"/api/v1/expenses/{expense_id}/approve",
        headers=ctx["manager"],
        json={"override": True},
    )
    assert no_comment.status_code == 422
    assert no_comment.json()["error"]["code"] == "COMMENT_REQUIRED"

    ok = client.post(
        f"/api/v1/expenses/{expense_id}/approve",
        headers=ctx["manager"],
        json={"override": True, "comment": "전문기관 사전 승인 공문 확보"},
    )
    assert ok.status_code == 200
    detail = client.get(f"/api/v1/expenses/{expense_id}", headers=ctx["manager"]).json()
    assert detail["approvals"][-1]["override"] is True


def test_reject_and_resubmit_cycle(client: TestClient, db: Session) -> None:
    ctx = _setup(client, db)
    expense_id = _create_expense(client, ctx)
    _force_status(db, expense_id, ExpenseStatus.NEEDS_REVIEW)

    res = client.post(
        f"/api/v1/expenses/{expense_id}/reject",
        headers=ctx["manager"],
        json={"reason": "증빙 금액 불일치"},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "REJECTED"

    # 작성자가 수정하면 DRAFT로 복귀 → 재제출 가능
    patch = client.patch(
        f"/api/v1/expenses/{expense_id}", headers=ctx["researcher"], json={"amount": 450000}
    )
    assert patch.status_code == 200
    assert patch.json()["status"] == "DRAFT"

    resubmit = client.post(f"/api/v1/expenses/{expense_id}/submit", headers=ctx["researcher"])
    assert resubmit.status_code == 200
    runs = db.execute(
        select(AutomationRun).where(AutomationRun.expense_id == expense_id)
    ).scalars().all()
    assert len(runs) == 1  # 이번 사이클의 실행 (거절 전 파이프라인은 없었음)


def test_approve_requires_manager_role(client: TestClient, db: Session) -> None:
    ctx = _setup(client, db)
    expense_id = _create_expense(client, ctx)
    _force_status(db, expense_id, ExpenseStatus.NEEDS_REVIEW)

    res = client.post(
        f"/api/v1/expenses/{expense_id}/approve", headers=ctx["researcher"], json={}
    )
    assert res.status_code == 403


def test_history_timeline(client: TestClient, db: Session) -> None:
    ctx = _setup(client, db)
    expense_id = _create_expense(client, ctx)
    client.post(f"/api/v1/expenses/{expense_id}/submit", headers=ctx["researcher"])

    res = client.get(f"/api/v1/expenses/{expense_id}/history", headers=ctx["researcher"])
    assert res.status_code == 200
    types = [e["type"] for e in res.json()]
    assert "audit:create" in types
    assert "audit:submit" in types
    assert any(t.startswith("pipeline:") for t in types)
