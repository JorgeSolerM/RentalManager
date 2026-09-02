from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.iban import format_iban, mask_iban
from backend.database.base import Base


class OwnerBankAccount(Base):
    __tablename__ = "owner_bank_accounts"
    __table_args__ = (
        UniqueConstraint("owner_id", "iban", name="uq_owner_bank_accounts_owner_iban"),
        CheckConstraint(
            "length(trim(account_holder_name)) > 0",
            name="ck_owner_bank_accounts_holder_not_blank",
        ),
        CheckConstraint(
            "length(currency) = 3 AND currency = upper(currency)",
            name="ck_owner_bank_accounts_currency",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("owners.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    account_holder_name: Mapped[str] = mapped_column(String(180), nullable=False)
    iban: Mapped[str] = mapped_column(String(34), nullable=False)
    bic: Mapped[str | None] = mapped_column(String(11), nullable=True)
    alias: Mapped[str | None] = mapped_column(String(100), nullable=True)
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="EUR", server_default="EUR"
    )
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )
    receives_rent: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    receives_settlements: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    owner: Mapped["Owner"] = relationship(back_populates="bank_accounts")
    rent_ownerships: Mapped[list["PropertyOwnership"]] = relationship(
        back_populates="rent_bank_account",
        foreign_keys="PropertyOwnership.rent_bank_account_id",
        passive_deletes="all",
    )

    @property
    def formatted_iban(self) -> str:
        return format_iban(self.iban)

    @property
    def masked_iban(self) -> str:
        return mask_iban(self.iban)
