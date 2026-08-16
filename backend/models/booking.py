from datetime import date

from sqlalchemy import Date, ForeignKey, Index, Integer, Numeric, String, Text, text
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
    )
