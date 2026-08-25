from sqlalchemy import CheckConstraint, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.base import Base


class RoomPublicHighlight(Base):
    __tablename__ = "room_public_highlights"
    __table_args__ = (
        UniqueConstraint("room_id", "position", name="uq_room_public_highlights_position"),
        CheckConstraint("position >= 0 AND position < 4", name="ck_room_public_highlights_position"),
    )

    room_id: Mapped[int] = mapped_column(
        ForeignKey("rooms.id", ondelete="CASCADE"), primary_key=True
    )
    feature_id: Mapped[int] = mapped_column(
        ForeignKey("features.id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    room: Mapped["Room"] = relationship(back_populates="public_highlights")
    feature: Mapped["Feature"] = relationship(back_populates="room_public_highlights")
