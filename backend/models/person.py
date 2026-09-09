from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.base import Base
from backend.core.iban import format_iban, mask_iban


class Person(Base):
    __tablename__ = "persons"
    __table_args__ = (
        CheckConstraint("length(trim(full_name)) > 0", name="ck_persons_full_name_not_blank"),
        CheckConstraint("document_type IS NULL OR document_type IN ('dni','nie','passport','other')", name="ck_persons_document_type"),
        CheckConstraint("verification_status IN ('unverified','verified')", name="ck_persons_verification_status"),
        CheckConstraint("source IN ('manual','legacy_guest')", name="ck_persons_source"),
        CheckConstraint("document_issuer_country IS NULL OR (length(document_issuer_country) = 2 AND document_issuer_country = upper(document_issuer_country))", name="ck_persons_document_issuer_country"),
        CheckConstraint("nationality IS NULL OR (length(nationality) = 2 AND nationality = upper(nationality))", name="ck_persons_nationality"),
        CheckConstraint("country IS NULL OR (length(country) = 2 AND country = upper(country))", name="ck_persons_country"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    iban: Mapped[str | None] = mapped_column(String(34), nullable=True)
    document_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    document_number: Mapped[str | None] = mapped_column(String(60), nullable=True)
    document_issuer_country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    nationality: Mapped[str | None] = mapped_column(String(2), nullable=True)
    address_line: Mapped[str | None] = mapped_column(String(255), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    province: Mapped[str | None] = mapped_column(String(120), nullable=True)
    country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    verification_status: Mapped[str] = mapped_column(String(20), nullable=False, default="unverified", server_default="unverified")
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="manual", server_default="manual")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

    booking_parties: Mapped[list["BookingParty"]] = relationship(back_populates="person", passive_deletes="all")
    sepa_mandates: Mapped[list["SepaMandate"]] = relationship(
        back_populates="person", order_by="SepaMandate.id", passive_deletes="all"
    )

    @property
    def formatted_iban(self) -> str:
        return format_iban(self.iban)

    @property
    def masked_iban(self) -> str:
        return mask_iban(self.iban)
