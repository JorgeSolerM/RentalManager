from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.base import Base


class Platform(Base):
    __tablename__ = "platforms"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    slug: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        unique=True,
    )

    favicon: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    supports_import: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    supports_export: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
