from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.base import Base


class RoomCalendar(Base):
    __tablename__ = "room_calendars"

    __table_args__ = (
        UniqueConstraint(
            "room_id",
            "platform_id",
            name="uq_room_platform",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )

    room_id: Mapped[int] = mapped_column(
        ForeignKey("rooms.id"),
        nullable=False,
    )

    platform_id: Mapped[int] = mapped_column(
        ForeignKey("platforms.id"),
        nullable=False,
    )

    import_url: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    last_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    last_sync_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    last_sync_status: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    last_sync_error: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    consecutive_failures: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    automatic_sync_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    room: Mapped["Room"] = relationship(
        back_populates="room_calendars",
    )

    platform: Mapped["Platform"] = relationship(
        back_populates="room_calendars",
    )

    bookings: Mapped[list["Booking"]] = relationship(
        back_populates="room_calendar",
        passive_deletes="all",
    )
