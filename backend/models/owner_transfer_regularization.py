"""Immutable recognition only. No banking or settlement adjustment effects."""
from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, Text, DateTime, Numeric, ForeignKey, JSON, CheckConstraint, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from backend.database.base import Base

class OwnerTransferRegularizationOperation(Base):
    __tablename__ = 'owner_transfer_regularizations'
    __table_args__ = (
        CheckConstraint("kind IN ('recognize','responsibility')"),
        CheckConstraint('amount > 0'),
        CheckConstraint("responsible IN ('pending','manager','owner')"),
        CheckConstraint("(kind='recognize' AND loss_id IS NULL) OR (kind='responsibility' AND loss_id IS NOT NULL AND responsible!='pending')"),
        CheckConstraint("(responsible='owner' AND responsible_owner_id IS NOT NULL AND length(trim(agreement))>0) OR (responsible!='owner' AND responsible_owner_id IS NULL)"),
        CheckConstraint('length(trim(reason))>0 AND length(trim(evidence))>0 AND length(trim(evidence_reference))>0'),
        UniqueConstraint('incident_id','recognition_key'),
        UniqueConstraint('loss_id'),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey('owner_transfer_incidents.id',ondelete='RESTRICT'),index=True)
    loss_id: Mapped[int|None] = mapped_column(ForeignKey('owner_transfer_regularizations.id',ondelete='RESTRICT'))
    kind: Mapped[str] = mapped_column(String(20))
    amount: Mapped[Decimal] = mapped_column(Numeric(12,2))
    responsible: Mapped[str] = mapped_column(String(12))
    responsible_owner_id: Mapped[int|None] = mapped_column(ForeignKey('owners.id',ondelete='RESTRICT'))
    agreement: Mapped[str] = mapped_column(Text,default='')
    reason: Mapped[str] = mapped_column(Text)
    evidence: Mapped[str] = mapped_column(Text)
    evidence_reference: Mapped[str] = mapped_column(String(160))
    recognition_key: Mapped[str|None] = mapped_column(String(64))
    operator_id: Mapped[str|None] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime,server_default=func.current_timestamp())
    before_state: Mapped[dict] = mapped_column(JSON)
    after_state: Mapped[dict] = mapped_column(JSON)
    request_key: Mapped[str] = mapped_column(String(36),unique=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    reviewed_state: Mapped[str] = mapped_column(String(64))
