"""카드 대사 매칭 로직 단위 테스트 — 순수 함수라 DB 없이 판정 규칙 자체를 검증한다."""

from datetime import date
from decimal import Decimal

from app.models.enums import CardMatchStatus
from app.services.reconciliation import (
    CardLine,
    _ExpenseKey,
    match_lines,
    parse_statement_csv,
)


def line(row_no=1, d="2026-08-20", biz="1018116293", amount=1_320_000, name="한빛사이언스"):
    return CardLine(
        row_no=row_no,
        approved_on=date.fromisoformat(d),
        merchant_name=name,
        merchant_biz_no=biz,
        amount=Decimal(amount),
        approval_no=None,
        card_no_masked=None,
    )


def exp(id=1, d="2026-08-20", biz="1018116293", amount=1_320_000):
    return _ExpenseKey(
        id=id, spent_at=date.fromisoformat(d), vendor_biz_no=biz, amount=Decimal(amount)
    )


def test_exact_match():
    results, unmatched = match_lines([line()], [exp()])
    assert results[0].status == CardMatchStatus.MATCHED
    assert results[0].expense_id == 1
    assert unmatched == []


def test_near_match_within_threshold_and_note():
    results, _ = match_lines([line(d="2026-08-22")], [exp(d="2026-08-20")])
    assert results[0].status == CardMatchStatus.MATCHED_NEAR
    assert "2일 차이" in (results[0].note or "")


def test_near_match_beyond_threshold_is_unmatched():
    # NEAR_DAYS=3 경계: 4일 차이는 매칭하지 않는다
    results, unmatched = match_lines([line(d="2026-08-24")], [exp(d="2026-08-20")])
    assert results[0].status == CardMatchStatus.UNMATCHED
    assert unmatched == [1]


def test_candidate_when_biz_no_missing():
    # 카드 라인에 사업자번호가 없어도 금액+일자가 맞으면 수기 확인 후보로 올린다
    results, _ = match_lines([line(biz=None)], [exp(biz=None)])
    assert results[0].status == CardMatchStatus.CANDIDATE


def test_amount_date_match_with_both_biz_present_is_not_candidate():
    # 양쪽 다 사업자번호가 있는데 서로 다르면 금액·일자가 같아도 다른 거래로 본다
    results, _ = match_lines([line(biz="1018116293")], [exp(biz="2208162517")])
    assert results[0].status == CardMatchStatus.UNMATCHED


def test_one_expense_never_matches_two_lines():
    # 같은 카드 라인이 두 줄(이중 청구 상황) — 집행 건이 하나면 한 줄만 매칭된다
    results, _ = match_lines([line(row_no=1), line(row_no=2)], [exp()])
    statuses = sorted(r.status for r in results)
    assert statuses == [CardMatchStatus.MATCHED, CardMatchStatus.UNMATCHED]


def test_exact_beats_near_for_contested_expense():
    # 정확 일치 라인이 근사 일치 라인보다 먼저 집행 건을 가져간다
    exact = line(row_no=1, d="2026-08-20")
    near = line(row_no=2, d="2026-08-21")
    results, _ = match_lines([near, exact], [exp()])
    by_row = {r.line.row_no: r for r in results}
    assert by_row[1].status == CardMatchStatus.MATCHED
    assert by_row[2].status == CardMatchStatus.UNMATCHED


def test_unmatched_expense_reported():
    results, unmatched = match_lines([line()], [exp(), exp(id=2, amount=999_999)])
    assert unmatched == [2]


def test_parse_csv_normalizes_biz_no_amount_and_date():
    csv_bytes = (
        "승인일자,가맹점명,가맹점사업자번호,승인금액,승인번호\n"
        '2026.08.20,한빛사이언스,101-81-16293,"1,320,000",30294117\n'
    ).encode("utf-8-sig")
    lines, errors = parse_statement_csv(csv_bytes)
    assert errors == []
    assert lines[0].merchant_biz_no == "1018116293"
    assert lines[0].amount == Decimal(1_320_000)
    assert lines[0].approved_on == date(2026, 8, 20)


def test_parse_csv_cp949_and_bad_row_skipped():
    csv_bytes = (
        "승인일자,가맹점명,승인금액\n2026-08-20,세움과학,3190000\n날짜아님,세움과학,3190000\n"
    ).encode("cp949")
    lines, errors = parse_statement_csv(csv_bytes)
    assert len(lines) == 1
    assert len(errors) == 1
