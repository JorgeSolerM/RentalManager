from datetime import date, datetime
import uuid

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.base import Base


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )

    room_id: Mapped[int] = mapped_column(
        ForeignKey("rooms.id"),
        nullable=False,
    )

    room_calendar_id: Mapped[int | None] = mapped_column(
        ForeignKey("room_calendars.id"),
        nullable=True,
    )

    guest_id: Mapped[int | None] = mapped_column(
        ForeignKey("guests.id"),
        nullable=True,
    )

    origin: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="manual",
    )

    external_reference: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    check_in: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    check_out: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    source_guest_name: Mapped[str | None] = mapped_column(
        String(160), nullable=True
    )

    expected_arrival_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    expected_departure_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    price: Mapped[float | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    room: Mapped["Room"] = relationship(
        back_populates="bookings",
    )

    room_calendar: Mapped["RoomCalendar"] = relationship(
        back_populates="bookings",
    )

    guest: Mapped["Guest"] = relationship(
        back_populates="bookings",
    )

    parties: Mapped[list["BookingParty"]] = relationship(
        back_populates="booking",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="BookingParty.id",
    )

    @property
    def operational_person_name(self) -> str:
        role_order = {"tenant": 0, "occupant": 1, "unclassified": 2, "payer": 3, "guarantor": 4}
        seen = set()
        names = []
        for party in sorted(self.parties, key=lambda item: (role_order.get(item.role, 99), item.id or 0)):
            if party.person_id in seen:
                continue
            seen.add(party.person_id)
            names.append(party.person.display_name or party.person.full_name)
        if names:
            return ", ".join(names)
        if self.source_guest_name:
            return self.source_guest_name
        if self.guest is not None:
            return self.guest.display_name or self.guest.full_name
        return "Huésped desconocido"

    financial_terms: Mapped[list["BookingFinancialTerms"]] = relationship(
        back_populates="booking", order_by="BookingFinancialTerms.version"
    )
    charges: Mapped[list["BookingCharge"]] = relationship(
        back_populates="booking", order_by="BookingCharge.due_date, BookingCharge.id"
    )
    payments: Mapped[list["Payment"]] = relationship(
        back_populates="booking", order_by="Payment.effective_date, Payment.id"
    )

    ical_uid: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default=lambda: uuid.uuid4().hex,
    )

    last_seen_in_feed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    @property
    def effective_arrival_date(self) -> date:
        return self.expected_arrival_date or self.check_in

    @property
    def effective_departure_date(self) -> date:
        return self.expected_departure_date or self.check_out

    __table_args__ = (
        Index(
            "uq_bookings_calendar_external_reference",
            "room_calendar_id",
            "external_reference",
            unique=True,
            sqlite_where=text(
                "room_calendar_id IS NOT NULL AND external_reference IS NOT NULL"
            ),
        ),
        Index(
            "uq_bookings_ical_uid",
            "ical_uid",
            unique=True,
        ),
    )
