from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.base import Base


class PropertyOwnership(Base):
    __tablename__ = "property_ownerships"
    __table_args__ = (
        CheckConstraint(
            "ownership_percentage > 0 AND ownership_percentage <= 100",
            name="ck_property_ownerships_percentage",
        ),
        CheckConstraint(
            "effective_until IS NULL OR effective_from IS NULL "
            "OR effective_until >= effective_from",
            name="ck_property_ownerships_effective_range",
        ),
        Index(
            "uq_property_ownerships_active_owner",
            "property_id",
            "owner_id",
            unique=True,
            sqlite_where=text("active = 1"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    property_id: Mapped[int] = mapped_column(
        ForeignKey("properties.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("owners.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    ownership_percentage: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False
    )
    rent_bank_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("owner_bank_accounts.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    property: Mapped["Property"] = relationship(back_populates="ownerships")
    owner: Mapped["Owner"] = relationship(back_populates="property_ownerships")
    rent_bank_account: Mapped["OwnerBankAccount | None"] = relationship(
        back_populates="rent_ownerships",
        foreign_keys=[rent_bank_account_id],
    )
