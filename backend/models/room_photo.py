from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Integer, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.base import Base


class RoomPhoto(Base):
    __tablename__ = "room_photos"
    __table_args__ = (
        CheckConstraint("position >= 0", name="ck_room_photos_position_nonnegative"),
        Index("uq_room_photos_asset", "room_id", "media_asset_id", unique=True),
        Index("uq_room_photos_position", "room_id", "position", unique=True),
        Index(
            "uq_room_photos_primary", "room_id", unique=True,
            sqlite_where=text("is_primary = 1"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    room_id: Mapped[int] = mapped_column(
        ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False
    )
    media_asset_id: Mapped[int] = mapped_column(
        ForeignKey("media_assets.id", ondelete="RESTRICT"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_primary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )

    room: Mapped["Room"] = relationship(back_populates="photos")
    asset: Mapped["MediaAsset"] = relationship(back_populates="room_photos")
