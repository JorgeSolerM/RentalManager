from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.base import Base


class BookingCharge(Base):
    __tablename__ = "booking_charges"
    __table_args__ = (
        CheckConstraint("type IN ('rent','security_deposit','reservation_deposit','utilities','extraordinary','discount','deposit_retention')", name="ck_booking_charges_type"),
        CheckConstraint("direction IN ('debit','credit')", name="ck_booking_charges_direction"),
        CheckConstraint("type != 'discount' OR direction = 'credit'", name="ck_booking_charges_discount_credit"),
        CheckConstraint("type = 'discount' OR direction = 'debit'", name="ck_booking_charges_non_discount_debit"),
        CheckConstraint("amount > 0", name="ck_booking_charges_amount_positive"),
        CheckConstraint("length(currency) = 3 AND currency = upper(currency)", name="ck_booking_charges_currency"),
        CheckConstraint("lifecycle IN ('draft','posted','void')", name="ck_booking_charges_lifecycle"),
        CheckConstraint("service_period_end IS NULL OR service_period_start IS NOT NULL", name="ck_booking_charges_period_start"),
        CheckConstraint("service_period_end IS NULL OR service_period_end > service_period_start", name="ck_booking_charges_period"),
        CheckConstraint("lifecycle != 'posted' OR posted_at IS NOT NULL", name="ck_booking_charges_posted"),
        CheckConstraint("lifecycle != 'void' OR voided_at IS NOT NULL", name="ck_booking_charges_voided"),
        Index("uq_booking_charges_generation_key", "booking_id", "generation_key", unique=True, sqlite_where=text("generation_key IS NOT NULL")),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id", ondelete="RESTRICT"), nullable=False, index=True)
    financial_terms_id: Mapped[int | None] = mapped_column(ForeignKey("booking_financial_terms.id", ondelete="RESTRICT"), nullable=True)
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False, default="debit")
    concept: Mapped[str] = mapped_column(String(255), nullable=False)
    service_period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    service_period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    due_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="EUR")
    lifecycle: Mapped[str] = mapped_column(String(10), nullable=False, default="draft")
    generation_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    corrects_charge_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())
    posted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    booking: Mapped["Booking"] = relationship(back_populates="charges")
    financial_terms: Mapped["BookingFinancialTerms | None"] = relationship(back_populates="charges")
    allocations: Mapped[list["PaymentAllocation"]] = relationship(back_populates="charge")
