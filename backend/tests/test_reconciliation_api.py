"""카드 대사 API 테스트: 업로드→판정 스냅샷, 권한, 잘못된 CSV."""

import io
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, CardReconciliationLine
from app.models.enums import ExpenseStatus, UserRole
from tests.conftest import create_account, login_headers
from tests.factories import make_expense, make_project, make_user


def _seed(db: Session) -> dict:
    project = make_project(db)
    researcher = make_user(db, email="r@corp.kr")
    # 승인 1건(카드와 정확 일치할 건), 승인 1건(카드에 없는 건), 반려 1건(대사 대상 제외)
    e1 = make_expense(db, project, researcher, amount=1_320_000, spent_at=date(2026, 8, 20))
    e1.vendor_biz_no = "1018116293"
    e1.status = ExpenseStatus.APPROVED
    e2 = make_expense(db, project, researcher, amount=3_600_000, spent_at=date(2026, 2, 20))
    e2.vendor_biz_no = "2208162517"
    e2.status = ExpenseStatus.APPROVED
    e3 = make_expense(db, project, researcher, amount=1_320_000, spent_at=date(2026, 8, 20))
    e3.vendor_biz_no = "1018116293"
    e3.status = ExpenseStatus.REJECTED
    db.commit()
    return {"project_id": project.id, "e1": e1.id, "e2": e2.id, "e3": e3.id}


def _upload(client: TestClient, headers: dict, project_id: int, csv_text: str, enc="utf-8-sig"):
    return client.post(
        f"/api/v1/projects/{project_id}/reconciliations",
        headers=headers,
        files={"file": ("card_2026_08.csv", io.BytesIO(csv_text.encode(enc)), "text/csv")},
    )


CSV = (
    "카드번호,승인일자,가맹점명,가맹점사업자번호,승인금액,승인번호\n"
    '9410-****-****-1207,2026-08-20,(주)한빛사이언스,101-81-16293,"1,320,000",30294117\n'
    "9410-****-****-1207,2026-08-19,스마트오피스몰,214-88-33437,88000,30291045\n"
)


def test_upload_reconciles_and_snapshots(client: TestClient, db: Session) -> None:
    ctx = _seed(db)
    create_account(db, email="mgr@corp.kr", role=UserRole.MANAGER)
    headers = login_headers(client, "mgr@corp.kr")

    res = _upload(client, headers, ctx["project_id"], CSV)
    assert res.status_code == 201, res.text
    body = res.json()

    assert body["total_lines"] == 2
    assert body["matched_count"] == 1
    assert body["unmatched_count"] == 1
    # 정확 일치 라인은 승인 건 e1에 붙는다 (반려 건 e3는 후보에서 제외됐다는 뜻이기도 하다)
    matched = next(ln for ln in body["lines"] if ln["match_status"] == "MATCHED")
    assert matched["matched_expense_id"] == ctx["e1"]
    # 카드에 없는 승인 건 e2는 미대사 집행으로 보고된다
    assert [e["id"] for e in body["unmatched_expenses"]] == [ctx["e2"]]
    # 감사 로그가 남는다
    log = db.execute(select(AuditLog).where(AuditLog.action == "card_recon_upload")).scalar_one()
    assert log.after["total"] == 2


def test_upload_requires_manager(client: TestClient, db: Session) -> None:
    ctx = _seed(db)
    create_account(db, email="res@corp.kr", role=UserRole.RESEARCHER)
    headers = login_headers(client, "res@corp.kr")
    res = _upload(client, headers, ctx["project_id"], CSV)
    assert res.status_code == 403


def test_upload_rejects_csv_without_required_columns(client: TestClient, db: Session) -> None:
    ctx = _seed(db)
    create_account(db, email="mgr@corp.kr", role=UserRole.MANAGER)
    headers = login_headers(client, "mgr@corp.kr")
    res = _upload(client, headers, ctx["project_id"], "아무거나,들어있는,파일\n1,2,3\n")
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "INVALID_STATEMENT"


def test_detail_returns_stored_lines(client: TestClient, db: Session) -> None:
    ctx = _seed(db)
    create_account(db, email="mgr@corp.kr", role=UserRole.MANAGER)
    headers = login_headers(client, "mgr@corp.kr")
    recon_id = _upload(client, headers, ctx["project_id"], CSV).json()["id"]

    res = client.get(f"/api/v1/reconciliations/{recon_id}", headers=headers)
    assert res.status_code == 200
    assert len(res.json()["lines"]) == 2
    # 라인이 실제로 저장돼 있다 (응답 조립이 아니라 스냅샷)
    stored = db.execute(select(CardReconciliationLine)).scalars().all()
    assert len(stored) == 2
