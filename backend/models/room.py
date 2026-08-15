from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.base import Base


class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )

    property_id: Mapped[int] = mapped_column(
        ForeignKey("properties.id"),
        nullable=False,
    )

    code: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    display_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )

    base_price: Mapped[float] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )

    square_meters: Mapped[float | None] = mapped_column(
        Numeric(5, 2),
        nullable=True,
    )

    active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    property: Mapped["Property"] = relationship(
        back_populates="rooms",
    )

    room_calendars: Mapped[list["RoomCalendar"]] = relationship(
        back_populates="room",
        passive_deletes="all",
    )

    bookings: Mapped[list["Booking"]] = relationship(
        back_populates="room",
        order_by="Booking.check_in",
        passive_deletes="all",
    )
