from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.base import Base


class MediaAsset(Base):
    __tablename__ = "media_assets"
    __table_args__ = (
        CheckConstraint("status IN ('processing', 'ready', 'failed')", name="ck_media_assets_status"),
        CheckConstraint("width > 0", name="ck_media_assets_width_positive"),
        CheckConstraint("height > 0", name="ck_media_assets_height_positive"),
        CheckConstraint("byte_size > 0", name="ck_media_assets_byte_size_positive"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    storage_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(50), nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="processing", server_default="processing"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    property_photos: Mapped[list["PropertyPhoto"]] = relationship(
        back_populates="asset", passive_deletes=True
    )
    room_photos: Mapped[list["RoomPhoto"]] = relationship(
        back_populates="asset", passive_deletes=True
    )
