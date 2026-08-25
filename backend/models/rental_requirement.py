from sqlalchemy import Boolean, CheckConstraint, Column, ForeignKey, Integer, String, Table, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.base import Base


property_requirements = Table(
    "property_requirements",
    Base.metadata,
    Column("property_id", ForeignKey("properties.id", ondelete="CASCADE"), primary_key=True),
    Column(
        "requirement_id",
        ForeignKey("rental_requirements.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    ),
)


class RentalRequirement(Base):
    __tablename__ = "rental_requirements"
    __table_args__ = (
        CheckConstraint(
            "display_order >= 0",
            name="ck_rental_requirements_display_order_nonnegative",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    public_name: Mapped[str] = mapped_column(String(140), nullable=False)
    public_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )
    display_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    properties: Mapped[list["Property"]] = relationship(
        secondary=property_requirements, back_populates="requirements"
    )
