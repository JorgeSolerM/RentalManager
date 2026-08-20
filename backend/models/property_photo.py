from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Integer, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.base import Base


class PropertyPhoto(Base):
    __tablename__ = "property_photos"
    __table_args__ = (
        CheckConstraint("position >= 0", name="ck_property_photos_position_nonnegative"),
        Index("uq_property_photos_asset", "property_id", "media_asset_id", unique=True),
        Index("uq_property_photos_position", "property_id", "position", unique=True),
        Index(
            "uq_property_photos_primary", "property_id", unique=True,
            sqlite_where=text("is_primary = 1"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    property_id: Mapped[int] = mapped_column(
        ForeignKey("properties.id", ondelete="CASCADE"), nullable=False
    )
    media_asset_id: Mapped[int] = mapped_column(
        ForeignKey("media_assets.id", ondelete="RESTRICT"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_primary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )

    property: Mapped["Property"] = relationship(back_populates="photos")
    asset: Mapped["MediaAsset"] = relationship(back_populates="property_photos")
