from sqlalchemy import Boolean, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.base import Base
from backend.models.feature import property_features


class Property(Base):
    __tablename__ = "properties"
    __table_args__ = (
        Index(
            "uq_properties_public_slug",
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

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    alias: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    address: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    city: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    owner: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    public_title: Mapped[str | None] = mapped_column(String(160), nullable=True)
    public_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    public_location: Mapped[str | None] = mapped_column(String(160), nullable=True)
    public_slug: Mapped[str | None] = mapped_column(String(180), nullable=True)
    is_published: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="0",
        nullable=False,
    )

    rooms: Mapped[list["Room"]] = relationship(
        back_populates="property",
        order_by="Room.display_order",
        passive_deletes="all",
    )

    features: Mapped[list["Feature"]] = relationship(
        secondary=property_features,
        back_populates="properties",
        order_by="Feature.display_order, Feature.name",
    )

    photos: Mapped[list["PropertyPhoto"]] = relationship(
        back_populates="property",
        order_by="PropertyPhoto.position, PropertyPhoto.id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
