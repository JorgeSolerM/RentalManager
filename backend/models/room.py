import secrets

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Integer, Numeric, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.base import Base
from backend.models.feature import room_features


class Room(Base):
    __tablename__ = "rooms"

    __table_args__ = (
        Index(
            "uq_rooms_master_calendar_token",
            "master_calendar_token",
            unique=True,
        ),
        CheckConstraint(
            "minimum_stay_months IS NULL OR minimum_stay_months >= 0",
            name="ck_rooms_minimum_stay_months_nonnegative",
        ),
        CheckConstraint(
            "maximum_stay_months IS NULL OR maximum_stay_months > 0",
            name="ck_rooms_maximum_stay_months_positive",
        ),
        CheckConstraint(
            "minimum_stay_months IS NULL OR maximum_stay_months IS NULL "
            "OR minimum_stay_months = 0 OR maximum_stay_months >= minimum_stay_months",
            name="ck_rooms_stay_months_compatible",
        ),
        CheckConstraint(
            "tenant_gender_preference IS NULL OR "
            "tenant_gender_preference IN ('any', 'male', 'female')",
            name="ck_rooms_tenant_gender_preference",
        ),
        Index(
            "uq_rooms_public_slug",
            "public_slug",
            unique=True,
            sqlite_where=text("public_slug IS NOT NULL"),
        ),
    )

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

    base_price: Mapped[float | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
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

    minimum_stay_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    maximum_stay_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tenant_gender_preference: Mapped[str | None] = mapped_column(
        String(10), nullable=True, default="any"
    )

    public_title: Mapped[str | None] = mapped_column(String(160), nullable=True)
    public_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    public_slug: Mapped[str | None] = mapped_column(String(180), nullable=True)
    is_published: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="0",
        nullable=False,
    )

    property: Mapped["Property"] = relationship(
        back_populates="rooms",
    )

    room_calendars: Mapped[list["RoomCalendar"]] = relationship(
        back_populates="room",
        passive_deletes="all",
    )

    master_calendar_token: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default=lambda: secrets.token_urlsafe(32),
    )

    bookings: Mapped[list["Booking"]] = relationship(
        back_populates="room",
        order_by="Booking.check_in",
        passive_deletes="all",
    )

    features: Mapped[list["Feature"]] = relationship(
        secondary=room_features,
        back_populates="rooms",
        order_by="Feature.display_order, Feature.name",
    )

    photos: Mapped[list["RoomPhoto"]] = relationship(
        back_populates="room",
        order_by="RoomPhoto.position, RoomPhoto.id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    public_highlights: Mapped[list["RoomPublicHighlight"]] = relationship(
        back_populates="room",
        order_by="RoomPublicHighlight.position",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
