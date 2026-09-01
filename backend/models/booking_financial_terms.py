from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.base import Base


class BookingFinancialTerms(Base):
    __tablename__ = "booking_financial_terms"
    __table_args__ = (
        UniqueConstraint("booking_id", "version", name="uq_booking_financial_terms_version"),
        CheckConstraint("version > 0", name="ck_booking_financial_terms_version_positive"),
        CheckConstraint("monthly_rent >= 0", name="ck_booking_financial_terms_rent_nonnegative"),
        CheckConstraint("deposit_agreed >= 0", name="ck_booking_financial_terms_deposit_nonnegative"),
        CheckConstraint("usual_due_day BETWEEN 1 AND 31", name="ck_booking_financial_terms_due_day"),
        CheckConstraint("length(currency) = 3 AND currency = upper(currency)", name="ck_booking_financial_terms_currency"),
        CheckConstraint("status IN ('draft','confirmed','superseded')", name="ck_booking_financial_terms_status"),
        CheckConstraint("effective_until IS NULL OR effective_until > effective_from", name="ck_booking_financial_terms_period"),
        CheckConstraint("status != 'confirmed' OR confirmed_at IS NOT NULL", name="ck_booking_financial_terms_confirmation"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id", ondelete="RESTRICT"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    monthly_rent: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="EUR")
    usual_due_day: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    deposit_agreed: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    supersedes_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    booking: Mapped["Booking"] = relationship(back_populates="financial_terms")
    charges: Mapped[list["BookingCharge"]] = relationship(back_populates="financial_terms")
