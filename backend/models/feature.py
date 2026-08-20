from sqlalchemy import Boolean, CheckConstraint, Column, ForeignKey, Integer, String, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.base import Base


property_features = Table(
    "property_features",
    Base.metadata,
    Column("property_id", ForeignKey("properties.id", ondelete="CASCADE"), primary_key=True),
    Column("feature_id", ForeignKey("features.id", ondelete="CASCADE"), primary_key=True),
)

room_features = Table(
    "room_features",
    Base.metadata,
    Column("room_id", ForeignKey("rooms.id", ondelete="CASCADE"), primary_key=True),
    Column("feature_id", ForeignKey("features.id", ondelete="CASCADE"), primary_key=True),
)


class Feature(Base):
    __tablename__ = "features"
    __table_args__ = (
        CheckConstraint("scope IN ('property', 'room', 'both')", name="ck_features_scope"),
        CheckConstraint("display_order >= 0", name="ck_features_display_order_nonnegative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    scope: Mapped[str] = mapped_column(String(20), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    icon_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")

    properties: Mapped[list["Property"]] = relationship(
        secondary=property_features, back_populates="features"
    )
    rooms: Mapped[list["Room"]] = relationship(
        secondary=room_features, back_populates="features"
    )
