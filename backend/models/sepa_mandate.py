from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.iban import format_iban, mask_iban
from backend.database.base import Base


SEPA_MANDATE_TYPES = ("RCUR", "OOFF")
SEPA_MANDATE_STATUSES = ("draft", "active", "cancelled", "expired")


class SepaMandate(Base):
    __tablename__ = "sepa_mandates"
    __table_args__ = (
        UniqueConstraint("creditor_profile_id", "mandate_reference", name="uq_sepa_mandates_creditor_reference"),
        CheckConstraint("mandate_type IN ('RCUR','OOFF')", name="ck_sepa_mandates_type"),
        CheckConstraint("status IN ('draft','active','cancelled','expired')", name="ck_sepa_mandates_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    creditor_profile_id: Mapped[int] = mapped_column(ForeignKey("sepa_creditor_profiles.id", ondelete="RESTRICT"), nullable=False, index=True)
    person_id: Mapped[int | None] = mapped_column(ForeignKey("persons.id", ondelete="RESTRICT"), nullable=True, index=True)
    debtor_name: Mapped[str] = mapped_column(String(180), nullable=False)
    debtor_iban: Mapped[str] = mapped_column(String(34), nullable=False)
    debtor_bic: Mapped[str | None] = mapped_column(String(11), nullable=True)
    mandate_reference: Mapped[str] = mapped_column(String(35), nullable=False)
    signature_date: Mapped[date] = mapped_column(Date, nullable=False)
    mandate_type: Mapped[str] = mapped_column(String(10), nullable=False, default="RCUR", server_default="RCUR")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft", server_default="draft")
    amendment_indicator: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    active_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    cancelled_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_used_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

    creditor_profile: Mapped["SepaCreditorProfile"] = relationship(back_populates="mandates")
    person: Mapped["Person | None"] = relationship(back_populates="sepa_mandates")
    booking_links: Mapped[list["BookingSepaMandate"]] = relationship(back_populates="mandate", passive_deletes="all")

    @property
    def formatted_iban(self) -> str:
        return format_iban(self.debtor_iban)

    @property
    def masked_iban(self) -> str:
        return mask_iban(self.debtor_iban)
