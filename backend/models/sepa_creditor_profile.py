from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.base import Base


class SepaCreditorProfile(Base):
    __tablename__ = "sepa_creditor_profiles"
    __table_args__ = (
        CheckConstraint("scheme IN ('CORE')", name="ck_sepa_creditor_profiles_scheme"),
        Index(
            "uq_sepa_creditor_profiles_active_account",
            "bank_account_id",
            unique=True,
            sqlite_where=text("active = 1"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mandate_reference_counter: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    display_name: Mapped[str] = mapped_column(String(180), nullable=False)
    creditor_name: Mapped[str] = mapped_column(String(180), nullable=False)
    creditor_identifier: Mapped[str] = mapped_column(String(35), nullable=False)
    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("owners.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    bank_account_id: Mapped[int] = mapped_column(
        ForeignKey("owner_bank_accounts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    scheme: Mapped[str] = mapped_column(String(10), nullable=False, default="CORE", server_default="CORE")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

    owner: Mapped["Owner | None"] = relationship(back_populates="sepa_creditor_profiles")
    bank_account: Mapped["OwnerBankAccount"] = relationship(back_populates="sepa_creditor_profiles")
    mandates: Mapped[list["SepaMandate"]] = relationship(back_populates="creditor_profile", order_by="SepaMandate.id", passive_deletes="all")
