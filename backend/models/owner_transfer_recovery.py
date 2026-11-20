"""Immutable received recoveries and supporting audit, never bank instructions."""
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import String, Text, Date, DateTime, Numeric, ForeignKey, JSON, Boolean, CheckConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from backend.database.base import Base


class OwnerTransferRecovery(Base):
    __tablename__ = 'owner_transfer_recoveries'
    __table_args__ = (CheckConstraint('amount>0'), CheckConstraint('received=1'),
        CheckConstraint("length(trim(reason))>0 AND length(trim(evidence))>0 AND length(trim(bank_reference))>0"))
    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey('owner_transfer_incidents.id', ondelete='RESTRICT'), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12,2))
    effective_date: Mapped[date] = mapped_column(Date)
    receiving_account_hash: Mapped[str] = mapped_column(String(64))
    receiving_account_suffix: Mapped[str] = mapped_column(String(4))
    bank_reference: Mapped[str] = mapped_column(String(255))
    bank_transaction_id: Mapped[str | None] = mapped_column(String(160))
    reason: Mapped[str] = mapped_column(Text)
    evidence: Mapped[str] = mapped_column(Text)
    received: Mapped[bool] = mapped_column(Boolean)
    operator_id: Mapped[str | None] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    request_key: Mapped[str] = mapped_column(String(36), unique=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    reviewed_state: Mapped[str] = mapped_column(String(64))
    allocations: Mapped[dict] = mapped_column(JSON)
    impact: Mapped[dict] = mapped_column(JSON)


class OwnerRecoveryAttribution(Base):
    __tablename__ = 'owner_recovery_attributions'
    id: Mapped[int] = mapped_column(primary_key=True)
    recovery_id: Mapped[int] = mapped_column(ForeignKey('owner_transfer_recoveries.id', ondelete='RESTRICT'), unique=True)
    allocations: Mapped[dict] = mapped_column(JSON)
    reason: Mapped[str] = mapped_column(Text)
    operator_id: Mapped[str | None] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    request_key: Mapped[str] = mapped_column(String(36), unique=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    reviewed_state: Mapped[str] = mapped_column(String(64))


class OwnerRecoveryReturnLink(Base):
    __tablename__ = 'owner_recovery_return_links'
    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey('owner_transfer_incidents.id', ondelete='RESTRICT'))
    return_id: Mapped[int] = mapped_column(ForeignKey('owner_payout_returns.id', ondelete='RESTRICT'), unique=True)
    reason: Mapped[str] = mapped_column(Text)
    operator_id: Mapped[str | None] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    request_key: Mapped[str] = mapped_column(String(36), unique=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    reviewed_state: Mapped[str] = mapped_column(String(64))


class OwnerBankCreditIdentity(Base):
    __tablename__ = 'owner_bank_credit_identities'
    __table_args__ = (CheckConstraint('(return_id IS NULL AND recovery_id IS NOT NULL) OR (return_id IS NOT NULL AND recovery_id IS NULL)'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    return_id: Mapped[int | None] = mapped_column(ForeignKey('owner_payout_returns.id', ondelete='RESTRICT'), unique=True)
    recovery_id: Mapped[int | None] = mapped_column(ForeignKey('owner_transfer_recoveries.id', ondelete='RESTRICT'), unique=True)
    bank_key: Mapped[str] = mapped_column(String(64), unique=True)


class OwnerPayoutReview(Base):
    __tablename__ = 'owner_payout_reviews'
    id: Mapped[int] = mapped_column(primary_key=True)
    payout_id: Mapped[int] = mapped_column(ForeignKey('owner_payouts.id', ondelete='RESTRICT'), unique=True)
    reason: Mapped[str] = mapped_column(Text)
    operator_id: Mapped[str | None] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    fingerprint: Mapped[str] = mapped_column(String(64))
    reviewed_state: Mapped[str] = mapped_column(String(64))
    values: Mapped[dict] = mapped_column(JSON)
    impact: Mapped[dict] = mapped_column(JSON)
