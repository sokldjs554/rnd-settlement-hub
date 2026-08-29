"""연구비카드 사용내역 대사 — CSV 파싱 + 결정론적 매칭.

매칭이 AI가 아니라 코드인 이유: 사업자번호·금액·일자의 비교는 정답이 정의되는
문제라서다. AI는 정답이 없는 추출·제안에만 쓴다(이 시스템의 역할 분리 원칙).

매칭 단계 (위에서부터, 각 집행 건은 한 라인에만 배정된다)
  1. MATCHED       사업자번호 + 금액 + 일자 전부 일치
  2. MATCHED_NEAR  사업자번호 + 금액 일치, 승인일-집행일 차이 ≤ NEAR_DAYS
                   (카드 승인일과 실제 거래일이 다른 합법적 경우가 흔하다 — R-EVD-003과 같은 근거)
  3. CANDIDATE     금액 + 일자 일치인데 사업자번호가 한쪽이라도 없음 — 수기 확인 대상
  4. UNMATCHED     대응 없음 — 미등록 집행 의심

같은 (사업자번호, 금액, 일자) 카드 라인이 두 줄이면 집행 건이 하나뿐일 때
둘째 줄은 UNMATCHED로 남는다. 이중 청구(R-DUP-001)가 카드 쪽에서도 드러나는 구조다.
"""

import csv
import io
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.errors import AppError
from app.models import CardReconciliation, CardReconciliationLine, Expense, Project, User
from app.models.enums import CardMatchStatus, ExpenseStatus
from app.services import audit

MAX_SIZE_BYTES = 1 * 1024 * 1024  # 카드 내역 CSV는 텍스트다 — 1MB면 수천 행
MAX_ROWS = 2000
NEAR_DAYS = 3  # 승인일-집행일 허용 차이. 코드 상수로 노출(내부 판단은 조정 가능해야 한다)

# CSV 헤더 이름 → 내부 필드. 카드사마다 표기가 달라 동의어를 허용한다.
_HEADER_ALIASES: dict[str, str] = {
    "승인일자": "approved_on",
    "승인일": "approved_on",
    "이용일자": "approved_on",
    "가맹점명": "merchant_name",
    "가맹점": "merchant_name",
    "이용가맹점": "merchant_name",
    "가맹점사업자번호": "merchant_biz_no",
    "사업자번호": "merchant_biz_no",
    "사업자등록번호": "merchant_biz_no",
    "승인금액": "amount",
    "이용금액": "amount",
    "금액": "amount",
    "승인번호": "approval_no",
    "카드번호": "card_no_masked",
}
_REQUIRED_FIELDS = ("approved_on", "merchant_name", "amount")


@dataclass(frozen=True)
class CardLine:
    row_no: int
    approved_on: date
    merchant_name: str
    merchant_biz_no: str | None  # 숫자 10자리로 정규화됨
    amount: Decimal
    approval_no: str | None
    card_no_masked: str | None


@dataclass
class MatchResult:
    line: CardLine
    status: CardMatchStatus
    expense_id: int | None
    note: str | None


def _normalize_biz_no(raw: str | None) -> str | None:
    if raw is None:
        return None
    digits = re.sub(r"\D", "", raw)
    return digits if len(digits) == 10 else None


def _parse_date(raw: str) -> date | None:
    s = raw.strip().replace(".", "-").replace("/", "-")
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _parse_amount(raw: str) -> Decimal | None:
    s = raw.strip().replace(",", "").replace("원", "")
    if not s:
        return None
    try:
        value = Decimal(s)
    except InvalidOperation:
        return None
    return value if value > 0 else None


def parse_statement_csv(data: bytes) -> tuple[list[CardLine], list[str]]:
    """카드 사용내역 CSV를 파싱한다. (성공 라인들, 행 단위 오류 메시지들) 반환.

    인코딩은 utf-8(-sig) → cp949 순으로 시도한다. 국내 카드사 내려받기 파일은
    cp949가 흔하다.
    """
    if len(data) > MAX_SIZE_BYTES:
        raise AppError(413, "FILE_TOO_LARGE", "CSV가 1MB를 넘습니다.")
    text = None
    for enc in ("utf-8-sig", "cp949"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise AppError(
            422, "INVALID_STATEMENT", "CSV 인코딩을 해석할 수 없습니다 (utf-8/cp949 지원)."
        )

    reader = csv.reader(io.StringIO(text))
    rows = [r for r in reader if any(cell.strip() for cell in r)]
    if not rows:
        raise AppError(422, "INVALID_STATEMENT", "CSV에 데이터가 없습니다.")

    header = [_HEADER_ALIASES.get(h.strip(), None) for h in rows[0]]
    missing = [f for f in _REQUIRED_FIELDS if f not in header]
    if missing:
        raise AppError(
            422,
            "INVALID_STATEMENT",
            "필수 컬럼이 없습니다: 승인일자·가맹점명·승인금액",
            {"missing": missing, "header": rows[0]},
        )
    if len(rows) - 1 > MAX_ROWS:
        raise AppError(422, "INVALID_STATEMENT", f"행이 너무 많습니다 (최대 {MAX_ROWS}행).")

    lines: list[CardLine] = []
    errors: list[str] = []
    for row_no, row in enumerate(rows[1:], start=1):
        record = {field: row[i].strip() for i, field in enumerate(header) if field and i < len(row)}
        approved_on = _parse_date(record.get("approved_on", ""))
        amount = _parse_amount(record.get("amount", ""))
        merchant = record.get("merchant_name", "")
        if approved_on is None or amount is None or not merchant:
            errors.append(f"{row_no}행: 승인일자/가맹점명/승인금액을 읽을 수 없어 건너뜀")
            continue
        lines.append(
            CardLine(
                row_no=row_no,
                approved_on=approved_on,
                merchant_name=merchant,
                merchant_biz_no=_normalize_biz_no(record.get("merchant_biz_no")),
                amount=amount,
                approval_no=record.get("approval_no") or None,
                card_no_masked=record.get("card_no_masked") or None,
            )
        )
    if not lines:
        raise AppError(422, "INVALID_STATEMENT", "읽을 수 있는 행이 없습니다.", {"errors": errors})
    return lines, errors


@dataclass(frozen=True)
class _ExpenseKey:
    """매칭에 필요한 집행 건 최소 정보 (순수 함수가 ORM에 의존하지 않게)."""

    id: int
    spent_at: date
    vendor_biz_no: str | None
    amount: Decimal


def match_lines(
    lines: list[CardLine], expenses: list[_ExpenseKey], *, near_days: int = NEAR_DAYS
) -> tuple[list[MatchResult], list[int]]:
    """카드 라인과 집행 건을 1:1로 대사한다. 순수 함수 — DB 없이 테스트된다.

    반환: (라인별 판정, 어떤 라인에도 배정되지 않은 집행 건 id 목록)
    """
    used: set[int] = set()
    results: list[MatchResult] = [
        MatchResult(line, CardMatchStatus.UNMATCHED, None, None) for line in lines
    ]

    def assign(tier: CardMatchStatus, candidates_of) -> None:
        # 같은 티어 안에서는 일자 차이가 작은 배정을 먼저 확정한다
        pending: list[tuple[int, int, MatchResult, _ExpenseKey]] = []
        for res in results:
            if res.status != CardMatchStatus.UNMATCHED:
                continue
            for exp in candidates_of(res.line):
                if exp.id in used:
                    continue
                gap = abs((res.line.approved_on - exp.spent_at).days)
                pending.append((gap, res.line.row_no, res, exp))
        for gap, _, res, exp in sorted(pending, key=lambda t: (t[0], t[1])):
            if res.status != CardMatchStatus.UNMATCHED or exp.id in used:
                continue
            used.add(exp.id)
            res.status = tier
            res.expense_id = exp.id
            if tier == CardMatchStatus.MATCHED_NEAR:
                res.note = f"카드 승인일과 집행일이 {gap}일 차이"
            elif tier == CardMatchStatus.CANDIDATE:
                res.note = "사업자번호 없이 금액·일자만 일치 — 수기 확인 필요"

    by_exact: dict[tuple[str, Decimal, date], list[_ExpenseKey]] = {}
    by_biz_amount: dict[tuple[str, Decimal], list[_ExpenseKey]] = {}
    by_amount_date: dict[tuple[Decimal, date], list[_ExpenseKey]] = {}
    for exp in expenses:
        if exp.vendor_biz_no:
            by_exact.setdefault((exp.vendor_biz_no, exp.amount, exp.spent_at), []).append(exp)
            by_biz_amount.setdefault((exp.vendor_biz_no, exp.amount), []).append(exp)
        by_amount_date.setdefault((exp.amount, exp.spent_at), []).append(exp)

    assign(
        CardMatchStatus.MATCHED,
        lambda ln: (
            by_exact.get((ln.merchant_biz_no, ln.amount, ln.approved_on), [])
            if ln.merchant_biz_no
            else []
        ),
    )
    assign(
        CardMatchStatus.MATCHED_NEAR,
        lambda ln: (
            [
                e
                for e in by_biz_amount.get((ln.merchant_biz_no, ln.amount), [])
                if abs((ln.approved_on - e.spent_at).days) <= near_days
            ]
            if ln.merchant_biz_no
            else []
        ),
    )
    # CANDIDATE: 사업자번호가 카드 라인 또는 집행 건 어느 한쪽이라도 없어 위 단계로 못 간 경우
    assign(
        CardMatchStatus.CANDIDATE,
        lambda ln: [
            e
            for e in by_amount_date.get((ln.amount, ln.approved_on), [])
            if ln.merchant_biz_no is None or e.vendor_biz_no is None
        ],
    )

    unmatched_expenses = [e.id for e in expenses if e.id not in used]
    return results, unmatched_expenses


def run_reconciliation(
    db: Session, project_id: int, *, file_name: str, data: bytes, user: User
) -> CardReconciliation:
    """업로드 → 파싱 → 대사 → 스냅샷 저장. 순수 계산이라 큐 없이 동기 처리한다.

    (큐는 AI·국세청처럼 느리고 실패하는 외부 호출을 위한 것이다 — DESIGN.md)
    """
    project = db.get(Project, project_id)
    if project is None:
        raise AppError(404, "NOT_FOUND", f"과제 {project_id}를 찾을 수 없습니다.")

    lines, parse_errors = parse_statement_csv(data)

    rows = db.execute(
        select(Expense.id, Expense.spent_at, Expense.vendor_biz_no, Expense.amount).where(
            Expense.project_id == project_id,
            Expense.status != ExpenseStatus.REJECTED,  # 반려 건과의 대사는 의미가 없다
            Expense.deleted_at.is_(None),
        )
    ).all()
    expenses = [_ExpenseKey(r.id, r.spent_at, r.vendor_biz_no, r.amount) for r in rows]

    results, unmatched_expense_ids = match_lines(lines, expenses)

    counts = {status: 0 for status in CardMatchStatus}
    for res in results:
        counts[res.status] += 1

    recon = CardReconciliation(
        project_id=project_id,
        uploaded_by=user.id,
        file_name=file_name,
        total_lines=len(results),
        matched_count=counts[CardMatchStatus.MATCHED],
        matched_near_count=counts[CardMatchStatus.MATCHED_NEAR],
        candidate_count=counts[CardMatchStatus.CANDIDATE],
        unmatched_count=counts[CardMatchStatus.UNMATCHED],
        unmatched_expense_ids=unmatched_expense_ids,
    )
    db.add(recon)
    db.flush()
    for res in results:
        db.add(
            CardReconciliationLine(
                reconciliation_id=recon.id,
                row_no=res.line.row_no,
                approved_on=res.line.approved_on,
                merchant_name=res.line.merchant_name,
                merchant_biz_no=res.line.merchant_biz_no,
                amount=res.line.amount,
                approval_no=res.line.approval_no,
                card_no_masked=res.line.card_no_masked,
                match_status=res.status,
                matched_expense_id=res.expense_id,
                note=res.note,
            )
        )
    audit.log(
        db,
        actor_id=user.id,
        entity_type="reconciliation",
        entity_id=recon.id,
        action="card_recon_upload",
        after={
            "file_name": file_name,
            "total": len(results),
            "unmatched": counts[CardMatchStatus.UNMATCHED],
            "parse_errors": parse_errors[:20],
        },
    )
    db.commit()
    return recon
