from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin
from app.models.enums import ValidationSeverity, VendorStatus


class ValidationResult(Base):
    """룰 엔진 평가 결과. 파이프라인 실행(run_id) 단위로 쌓이는 불변 기록."""

    __tablename__ = "validation_results"
    __table_args__ = (
        Index("ix_validation_results_expense", "expense_id"),
        Index("ix_validation_results_rule_code", "rule_code"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    expense_id: Mapped[int] = mapped_column(
        ForeignKey("expenses.id", ondelete="CASCADE"), nullable=False
    )
    run_id: Mapped[int | None] = mapped_column(
        ForeignKey("automation_runs.id", ondelete="SET NULL")
    )
    rule_code: Mapped[str] = mapped_column(String(20), nullable=False)  # 예: R-VND-002
    severity: Mapped[ValidationSeverity] = mapped_column(
        Enum(ValidationSeverity, name="validation_severity"), nullable=False
    )
    message: Mapped[str] = mapped_column(String(500), nullable=False)
    detail: Mapped[dict | None] = mapped_column(JSONB)  # 판정 근거 데이터(비교값 등)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class VendorCheck(TimestampMixin, Base):
    """국세청 사업자 상태조회 결과 캐시. biz_no당 1행, TTL 경과 시 재조회로 갱신."""

    __tablename__ = "vendor_checks"

    id: Mapped[int] = mapped_column(primary_key=True)
    biz_no: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    status: Mapped[VendorStatus] = mapped_column(
        Enum(VendorStatus, name="vendor_status"), nullable=False
    )
    b_stt: Mapped[str | None] = mapped_column(String(20))  # 국세청 응답 원문(계속사업자 등)
    tax_type: Mapped[str | None] = mapped_column(String(100))
    end_dt: Mapped[str | None] = mapped_column(String(8))  # 폐업일(YYYYMMDD, 원문 그대로)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw: Mapped[dict | None] = mapped_column(JSONB)  # API 응답 원문
