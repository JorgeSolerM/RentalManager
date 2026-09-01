from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.base import Base


BOOKING_PARTY_ROLES = ("tenant", "occupant", "payer", "guarantor", "unclassified")


class BookingParty(Base):
    __tablename__ = "booking_parties"
    __table_args__ = (
        UniqueConstraint("booking_id", "person_id", "role", name="uq_booking_parties_booking_person_role"),
        CheckConstraint("role IN ('tenant','occupant','payer','guarantor','unclassified')", name="ck_booking_parties_role"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id", ondelete="CASCADE"), nullable=False, index=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("persons.id", ondelete="RESTRICT"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())

    booking: Mapped["Booking"] = relationship(back_populates="parties")
    person: Mapped["Person"] = relationship(back_populates="booking_parties")
