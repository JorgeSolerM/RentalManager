"""Immutable non-banking authorizations and consumption of documented agreements."""
from datetime import datetime
from decimal import Decimal
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, JSON, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from backend.database.base import Base


class AuditFields:
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    reason: Mapped[str] = mapped_column(Text)
    evidence: Mapped[str] = mapped_column(Text)
    operator_id: Mapped[str | None] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    before_state: Mapped[dict] = mapped_column(JSON)
    after_state: Mapped[dict] = mapped_column(JSON)
    request_key: Mapped[str] = mapped_column(String(36), unique=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    reviewed_state: Mapped[str] = mapped_column(String(64))


class OwnerLossCompensationAuthorization(AuditFields, Base):
    __tablename__ = 'owner_loss_compensation_authorizations'
    __table_args__ = (CheckConstraint('amount > 0'), CheckConstraint('length(trim(reason))>0 AND length(trim(evidence))>0 AND length(trim(agreement_reference))>0'))
    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey('owner_transfer_incidents.id', ondelete='RESTRICT'), index=True)
    loss_id: Mapped[int] = mapped_column(ForeignKey('owner_transfer_regularizations.id', ondelete='RESTRICT'), unique=True)
    responsibility_id: Mapped[int] = mapped_column(ForeignKey('owner_transfer_regularizations.id', ondelete='RESTRICT'), unique=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey('owners.id', ondelete='RESTRICT'), index=True)
    agreement_reference: Mapped[str] = mapped_column(String(160))
    agreement_key: Mapped[str] = mapped_column(String(64), unique=True)
    settlement_ids: Mapped[list] = mapped_column(JSON)


class OwnerLossCompensationApplication(AuditFields, Base):
    __tablename__ = 'owner_loss_compensation_applications'
    __table_args__ = (CheckConstraint('amount > 0'), CheckConstraint('length(trim(reason))>0 AND length(trim(evidence))>0'))
    id: Mapped[int] = mapped_column(primary_key=True)
    authorization_id: Mapped[int] = mapped_column(ForeignKey('owner_loss_compensation_authorizations.id', ondelete='RESTRICT'), index=True)
    settlement_id: Mapped[int] = mapped_column(ForeignKey('owner_settlements.id', ondelete='RESTRICT'), index=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey('owners.id', ondelete='RESTRICT'), index=True)
