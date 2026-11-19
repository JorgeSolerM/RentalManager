from datetime import datetime
from decimal import Decimal
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, JSON, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from backend.database.base import Base


class PaymentCorrectionOperation(Base):
    __tablename__ = 'payment_correction_operations'
    __table_args__ = (
        CheckConstraint("kind IN ('void','replace')", name='ck_payment_correction_kind'),
        CheckConstraint('before_amount > 0 AND after_amount >= 0', name='ck_payment_correction_amounts'),
        CheckConstraint("(kind='void' AND replacement_payment_id IS NULL AND after_amount=0) OR (kind='replace' AND replacement_payment_id IS NOT NULL AND after_amount>0)", name='ck_payment_correction_replacement'),
        CheckConstraint('length(trim(reason)) > 0', name='ck_payment_correction_reason'),
    )
    request_key: Mapped[str] = mapped_column(String(36), primary_key=True)
    original_payment_id: Mapped[int] = mapped_column(ForeignKey('payments.id', ondelete='RESTRICT'), unique=True)
    replacement_payment_id: Mapped[int | None] = mapped_column(ForeignKey('payments.id', ondelete='RESTRICT'), unique=True)
    kind: Mapped[str] = mapped_column(String(10))
    reason: Mapped[str] = mapped_column(Text)
    before_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    after_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    fingerprint: Mapped[str] = mapped_column(String(64))
    reviewed_state: Mapped[str] = mapped_column(String(64))
    distribution: Mapped[list] = mapped_column(JSON)
    custody_snapshot: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
