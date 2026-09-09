from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.base import Base


class Owner(Base):
    __tablename__ = "owners"
    __table_args__ = (
        CheckConstraint(
            "length(trim(legal_name)) > 0",
            name="ck_owners_legal_name_not_blank",
        ),
        CheckConstraint(
            "country IS NULL OR (length(country) = 2 AND country = upper(country))",
            name="ck_owners_country",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    legal_name: Mapped[str] = mapped_column(String(180), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(180), nullable=True)
    tax_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    address_line: Mapped[str | None] = mapped_column(String(255), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    province: Mapped[str | None] = mapped_column(String(120), nullable=True)
    country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    bank_accounts: Mapped[list["OwnerBankAccount"]] = relationship(
        back_populates="owner",
        order_by="OwnerBankAccount.id",
        passive_deletes="all",
    )
    property_ownerships: Mapped[list["PropertyOwnership"]] = relationship(
        back_populates="owner",
        order_by="PropertyOwnership.id",
        passive_deletes="all",
    )
    sepa_creditor_profiles: Mapped[list["SepaCreditorProfile"]] = relationship(
        back_populates="owner", order_by="SepaCreditorProfile.id", passive_deletes="all"
    )

    @property
    def name(self) -> str:
        return self.display_name or self.legal_name
