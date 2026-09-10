"""Private banking instructions, deliberately separate from the ledger."""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.base import Base


class SepaSettings(Base):
    __tablename__ = "sepa_settings"
    __table_args__ = (CheckConstraint("id = 1", name="ck_sepa_settings_singleton"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    initiator_name: Mapped[str | None] = mapped_column(String(70))
    initiator_identifier: Mapped[str | None] = mapped_column(String(35))


class SepaBatch(Base):
    __tablename__ = "sepa_batches"
    __table_args__ = (CheckConstraint("status IN ('prepared','exported','presented','partially_collected','collected','cancelled')", name="ck_sepa_batches_status"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reference: Mapped[str] = mapped_column(String(35), unique=True)
    name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    request_key: Mapped[str] = mapped_column(String(36), unique=True)
    period: Mapped[date] = mapped_column(Date)
    requested_collection_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(30), default="prepared")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    exported_at: Mapped[datetime | None] = mapped_column(DateTime)
    presented_at: Mapped[datetime | None] = mapped_column(DateTime)
    groups: Mapped[list["SepaBatchGroup"]] = relationship(back_populates="batch", order_by="SepaBatchGroup.id")

    @property
    def display_name(self):
        return self.name or f"Remesa {self.id}"


class SepaBatchGroup(Base):
    __tablename__ = "sepa_batch_groups"
    __table_args__ = (UniqueConstraint("batch_id", "creditor_profile_id", name="uq_sepa_group_creditor"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("sepa_batches.id", ondelete="RESTRICT"), index=True)
    creditor_profile_id: Mapped[int] = mapped_column(ForeignKey("sepa_creditor_profiles.id", ondelete="RESTRICT"))
    bank_account_id: Mapped[int] = mapped_column(ForeignKey("owner_bank_accounts.id", ondelete="RESTRICT"))
    # Immutable snapshot once created, never included in public schemas/logs.
    snapshot: Mapped[dict] = mapped_column(JSON)
    batch: Mapped["SepaBatch"] = relationship(back_populates="groups")
    debits: Mapped[list["SepaDebit"]] = relationship(back_populates="group", order_by="SepaDebit.id")
    artifact: Mapped["SepaExportArtifact | None"] = relationship(back_populates="group", uselist=False)


class SepaDebit(Base):
    __tablename__ = "sepa_debits"
    __table_args__ = (
        CheckConstraint("amount > 0 AND currency = 'EUR'", name="ck_sepa_debit_money"),
        CheckConstraint("status IN ('prepared','presented','collected','returned','cancelled')", name="ck_sepa_debit_status"),
        CheckConstraint("(status IN ('collected','returned') AND payment_id IS NOT NULL AND collected_at IS NOT NULL) OR (status NOT IN ('collected','returned') AND payment_id IS NULL AND collected_at IS NULL)", name="ck_sepa_debit_collection"),
        CheckConstraint("(status = 'returned' AND return_payment_id IS NOT NULL AND returned_on IS NOT NULL AND returned_at IS NOT NULL) OR (status != 'returned' AND return_payment_id IS NULL AND returned_on IS NULL AND returned_at IS NULL)", name="ck_sepa_debit_return"),
        CheckConstraint("(status = 'cancelled' AND cancelled_at IS NOT NULL) OR (status != 'cancelled' AND cancelled_at IS NULL)", name="ck_sepa_debit_cancel"),
        UniqueConstraint("group_id", "booking_id", "mandate_id", name="uq_sepa_debit_booking"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("sepa_batch_groups.id", ondelete="RESTRICT"), index=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id", ondelete="RESTRICT"), index=True)
    mandate_id: Mapped[int] = mapped_column(ForeignKey("sepa_mandates.id", ondelete="RESTRICT"))
    creditor_profile_id: Mapped[int] = mapped_column(ForeignKey("sepa_creditor_profiles.id", ondelete="RESTRICT"))
    payment_id: Mapped[int | None] = mapped_column(ForeignKey("payments.id", ondelete="RESTRICT"), unique=True)
    retry_of_id: Mapped[int | None] = mapped_column(ForeignKey("sepa_debits.id", ondelete="RESTRICT"))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    requested_collection_date: Mapped[date] = mapped_column(Date)
    end_to_end_id: Mapped[str] = mapped_column(String(35), unique=True)
    remittance_information: Mapped[str] = mapped_column(String(140))
    status: Mapped[str] = mapped_column(String(20), default="prepared")
    snapshot: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    collected_at: Mapped[datetime | None] = mapped_column(DateTime)
    return_payment_id: Mapped[int | None] = mapped_column(ForeignKey('payments.id', ondelete='RESTRICT'), unique=True)
    returned_on: Mapped[date | None] = mapped_column(Date)
    returned_at: Mapped[datetime | None] = mapped_column(DateTime)
    return_reason: Mapped[str | None] = mapped_column(String(255))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime)
    cancellation_reason: Mapped[str | None] = mapped_column(String(255))
    payment: Mapped['Payment | None'] = relationship(foreign_keys=[payment_id])
    return_payment: Mapped['Payment | None'] = relationship(foreign_keys=[return_payment_id])
    group: Mapped["SepaBatchGroup"] = relationship(back_populates="debits")
    allocations: Mapped[list["SepaDebitChargeAllocation"]] = relationship(back_populates="debit", order_by="SepaDebitChargeAllocation.id")


class SepaDebitChargeAllocation(Base):
    __tablename__ = "sepa_debit_charge_allocations"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_sepa_debit_allocation_amount"),
        UniqueConstraint("debit_id", "charge_id", name="uq_sepa_debit_charge"),
        Index("uq_sepa_charge_reservation", "charge_id", unique=True, sqlite_where=text("reserved = 1")),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    debit_id: Mapped[int] = mapped_column(ForeignKey("sepa_debits.id", ondelete="RESTRICT"), index=True)
    # Return/cancellation releases the reservation without deleting its history.
    charge_id: Mapped[int] = mapped_column(ForeignKey("booking_charges.id", ondelete="RESTRICT"))
    reserved: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    debit: Mapped["SepaDebit"] = relationship(back_populates="allocations")


class SepaExportArtifact(Base):
    __tablename__ = "sepa_export_artifacts"
    __table_args__ = (CheckConstraint("transaction_count > 0 AND control_sum > 0", name="ck_sepa_artifact_totals"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("sepa_batch_groups.id", ondelete="RESTRICT"), unique=True)
    filename: Mapped[str] = mapped_column(String(100), unique=True)
    sha256: Mapped[str] = mapped_column(String(64))
    format: Mapped[str] = mapped_column(String(40), default="BBVA pain.008.001.02")
    generated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    transaction_count: Mapped[int] = mapped_column(Integer)
    control_sum: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    group: Mapped["SepaBatchGroup"] = relationship(back_populates="artifact")
