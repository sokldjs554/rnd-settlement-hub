"""연구비카드 사용내역 대사.

카드사 API 연동이 없는 상태에서 손이 가장 많이 가는 수작업(README 한계점 1순위)을
줄이는 기능이다. 담당자가 카드사에서 내려받은 사용내역 CSV를 업로드하면
과제의 집행 건과 자동 대사한다.

설계 노트
- 업로드 1회 = card_reconciliations 1행(스냅샷). 대사 결과는 업로드 시점의
  집행 건 기준으로 고정해 저장한다 — 보고서 summary_json과 같은 태도로,
  나중에 집행 건이 바뀌어도 그때 무엇과 대조했는지가 남는다.
- 판정은 결정론이다. AI를 쓰지 않는다(문자열·숫자 비교면 충분한 문제다).
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import (
    Date,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import CardMatchStatus


class CardReconciliation(TimestampMixin, Base):
    """카드 사용내역 업로드 1건 — 대사 실행의 단위이자 결과 스냅샷."""

    __tablename__ = "card_reconciliations"
    __table_args__ = (Index("ix_card_reconciliations_project", "project_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)

    # 라인 판정 집계 (lines에서 유도 가능하지만 목록 화면이 매번 집계하지 않도록 저장)
    total_lines: Mapped[int] = mapped_column(Integer, nullable=False)
    matched_count: Mapped[int] = mapped_column(Integer, nullable=False)
    matched_near_count: Mapped[int] = mapped_column(Integer, nullable=False)
    candidate_count: Mapped[int] = mapped_column(Integer, nullable=False)
    unmatched_count: Mapped[int] = mapped_column(Integer, nullable=False)

    # 업로드 시점에 어떤 카드 라인과도 대응되지 않은 집행 건 id 스냅샷.
    # 결제수단 컬럼이 없는 현 스키마에서는 계좌이체 집행도 여기 섞인다(README 한계점 참고).
    unmatched_expense_ids: Mapped[list | None] = mapped_column(JSONB)

    lines: Mapped[list["CardReconciliationLine"]] = relationship(
        back_populates="reconciliation",
        cascade="all, delete-orphan",
        order_by="CardReconciliationLine.row_no",
    )


class CardReconciliationLine(TimestampMixin, Base):
    """카드 사용내역 CSV의 한 줄 + 대사 판정."""

    __tablename__ = "card_reconciliation_lines"
    __table_args__ = (
        Index("ix_card_recon_lines_recon", "reconciliation_id"),
        Index("ix_card_recon_lines_expense", "matched_expense_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    reconciliation_id: Mapped[int] = mapped_column(
        ForeignKey("card_reconciliations.id", ondelete="CASCADE"), nullable=False
    )
    row_no: Mapped[int] = mapped_column(Integer, nullable=False)  # CSV 데이터 행 번호(1부터)

    approved_on: Mapped[date] = mapped_column(Date, nullable=False)  # 카드 승인일
    merchant_name: Mapped[str] = mapped_column(String(255), nullable=False)
    merchant_biz_no: Mapped[str | None] = mapped_column(String(10))  # 숫자 10자리로 정규화
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 0), nullable=False)
    approval_no: Mapped[str | None] = mapped_column(String(20))
    card_no_masked: Mapped[str | None] = mapped_column(String(25))

    match_status: Mapped[CardMatchStatus] = mapped_column(
        Enum(CardMatchStatus, name="card_match_status"), nullable=False
    )
    matched_expense_id: Mapped[int | None] = mapped_column(
        ForeignKey("expenses.id", ondelete="SET NULL")
    )
    note: Mapped[str | None] = mapped_column(String(255))  # 판정 근거 한 줄

    reconciliation: Mapped[CardReconciliation] = relationship(back_populates="lines")
