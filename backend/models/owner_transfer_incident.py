"""Append-only records of real transfer incidents; no recoveries in phase 2."""
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import String, Text, Date, DateTime, Numeric, ForeignKey, JSON, Boolean, CheckConstraint, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from backend.database.base import Base

class OwnerTransferIncident(Base):
    __tablename__ = 'owner_transfer_incidents'
    __table_args__ = (
        CheckConstraint("kind IN ('wrong_account','wrong_recipient','unknown_recipient','duplicate')", name='ck_transfer_incident_kind'),
        CheckConstraint("source_kind IN ('payout','extraordinary')", name='ck_transfer_incident_source'),
        CheckConstraint("(source_kind='payout' AND payout_root_id IS NOT NULL) OR (source_kind='extraordinary' AND payout_root_id IS NULL)", name='ck_transfer_incident_link'),
        CheckConstraint('affected_amount>0', name='ck_transfer_incident_amount'),
        CheckConstraint('length(trim(reason))>0 AND length(trim(evidence))>0', name='ck_transfer_incident_evidence'),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    settlement_id: Mapped[int] = mapped_column(ForeignKey('owner_settlements.id', ondelete='RESTRICT'), index=True)
    intended_owner_id: Mapped[int] = mapped_column(ForeignKey('owners.id', ondelete='RESTRICT'), index=True)
    source_kind: Mapped[str] = mapped_column(String(20))
    payout_root_id: Mapped[int | None] = mapped_column(ForeignKey('owner_payouts.id', ondelete='RESTRICT'), unique=True)
    duplicate_of_root_id: Mapped[int | None] = mapped_column(ForeignKey('owner_payouts.id', ondelete='RESTRICT'))
    kind: Mapped[str] = mapped_column(String(24))
    affected_amount: Mapped[Decimal] = mapped_column(Numeric(12,2))
    recipient_owner_id: Mapped[int | None] = mapped_column(ForeignKey('owners.id', ondelete='RESTRICT'))
    recipient_description: Mapped[str | None] = mapped_column(String(180))
    receipt_accredited: Mapped[bool] = mapped_column(Boolean)
    reason: Mapped[str] = mapped_column(Text)
    evidence: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())

class OwnerTransferOutflow(Base):
    __tablename__ = 'owner_transfer_outflows'
    __table_args__ = (CheckConstraint('amount>0', name='ck_transfer_outflow_amount'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey('owner_transfer_incidents.id', ondelete='RESTRICT'), unique=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12,2))
    effective_date: Mapped[date] = mapped_column(Date)
    source_account_hash: Mapped[str | None] = mapped_column(String(64))
    source_account_suffix: Mapped[str | None] = mapped_column(String(4))
    destination_hash: Mapped[str | None] = mapped_column(String(64))
    destination_suffix: Mapped[str | None] = mapped_column(String(4))
    reference: Mapped[str] = mapped_column(String(255))
    bank_transaction_id: Mapped[str | None] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())

class OwnerTransferIncidentOperation(Base):
    __tablename__ = 'owner_transfer_incident_operations'
    __table_args__ = (CheckConstraint("kind IN ('register','attribute')", name='ck_transfer_incident_operation'), UniqueConstraint('incident_id','kind',name='uq_incident_operation_kind'))
    request_key: Mapped[str] = mapped_column(String(36), primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey('owner_transfer_incidents.id', ondelete='RESTRICT'), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(Text)
    operator_id: Mapped[str | None] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    before_state: Mapped[dict] = mapped_column(JSON)
    after_state: Mapped[dict] = mapped_column(JSON)
    fingerprint: Mapped[str] = mapped_column(String(64))
    reviewed_state: Mapped[str] = mapped_column(String(64))

class OwnerTransferIdentity(Base):
    __tablename__ = 'owner_transfer_identities'
    __table_args__ = (CheckConstraint('(payout_root_id IS NOT NULL AND outflow_id IS NULL) OR (payout_root_id IS NULL AND outflow_id IS NOT NULL)',name='ck_transfer_identity_source'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    payout_root_id: Mapped[int | None] = mapped_column(ForeignKey('owner_payouts.id', ondelete='RESTRICT'), unique=True)
    outflow_id: Mapped[int | None] = mapped_column(ForeignKey('owner_transfer_outflows.id', ondelete='RESTRICT'), unique=True)
    bank_key: Mapped[str] = mapped_column(String(64), unique=True)
    source_account_hash: Mapped[str | None] = mapped_column(String(64))
    bank_transaction_id: Mapped[str | None] = mapped_column(String(160))
