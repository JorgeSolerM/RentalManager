from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.base import Base


class BookingSepaMandate(Base):
    __tablename__ = "booking_sepa_mandates"
    __table_args__ = (
        UniqueConstraint("booking_id", "mandate_id", name="uq_booking_sepa_mandates_booking_mandate"),
        Index(
            "uq_booking_sepa_mandates_active_booking",
            "booking_id",
            unique=True,
            sqlite_where=text("active = 1"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id", ondelete="CASCADE"), nullable=False, index=True)
    mandate_id: Mapped[int] = mapped_column(ForeignKey("sepa_mandates.id", ondelete="RESTRICT"), nullable=False, index=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

    booking: Mapped["Booking"] = relationship(back_populates="sepa_mandate_links")
    mandate: Mapped["SepaMandate"] = relationship(back_populates="booking_links")
