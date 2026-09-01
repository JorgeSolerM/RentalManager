from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.base import Base


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_payments_amount_positive"),
        CheckConstraint("length(currency) = 3 AND currency = upper(currency)", name="ck_payments_currency"),
        CheckConstraint("direction IN ('receipt','refund')", name="ck_payments_direction"),
        CheckConstraint("method IN ('bank_transfer','cash','card_or_platform','sepa_direct_debit','other')", name="ck_payments_method"),
        CheckConstraint("lifecycle IN ('draft','posted','void')", name="ck_payments_lifecycle"),
        CheckConstraint("lifecycle != 'posted' OR posted_at IS NOT NULL", name="ck_payments_posted"),
        CheckConstraint("lifecycle != 'void' OR voided_at IS NOT NULL", name="ck_payments_voided"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id", ondelete="RESTRICT"), nullable=False, index=True)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="EUR")
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    method: Mapped[str] = mapped_column(String(30), nullable=False)
    external_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    lifecycle: Mapped[str] = mapped_column(String(10), nullable=False, default="draft")
    corrects_payment_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())
    posted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    booking: Mapped["Booking"] = relationship(back_populates="payments")
    allocations: Mapped[list["PaymentAllocation"]] = relationship(back_populates="payment")
