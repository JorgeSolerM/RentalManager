"""Append-only administrative history; original payouts remain immutable."""
from datetime import datetime
from sqlalchemy import String,Text,DateTime,ForeignKey,JSON,Boolean,CheckConstraint,func
from sqlalchemy.orm import Mapped,mapped_column
from backend.database.base import Base

class OwnerPayoutCorrectionOperation(Base):
    __tablename__='owner_payout_correction_operations'
    __table_args__=(
        CheckConstraint("kind IN ('void','replace')",name='ck_payout_correction_kind'),
        CheckConstraint("(kind='void' AND replacement_payout_id IS NULL AND no_transfer=1) OR (kind='replace' AND replacement_payout_id IS NOT NULL AND no_transfer=0)",name='ck_payout_correction_shape'),
        CheckConstraint('original_payout_id != replacement_payout_id',name='ck_payout_correction_distinct'),
        CheckConstraint('length(trim(reason))>0',name='ck_payout_correction_reason'),)
    request_key: Mapped[str]=mapped_column(String(36),primary_key=True)
    original_payout_id: Mapped[int]=mapped_column(ForeignKey('owner_payouts.id',ondelete='RESTRICT'),unique=True)
    replacement_payout_id: Mapped[int|None]=mapped_column(ForeignKey('owner_payouts.id',ondelete='RESTRICT'),unique=True)
    kind: Mapped[str]=mapped_column(String(12))
    reason: Mapped[str]=mapped_column(Text)
    no_transfer: Mapped[bool]=mapped_column(Boolean)
    operator_id: Mapped[str|None]=mapped_column(String(160))
    created_at: Mapped[datetime]=mapped_column(DateTime,server_default=func.current_timestamp())
    before_state: Mapped[dict]=mapped_column(JSON)
    after_state: Mapped[dict]=mapped_column(JSON)
    impact: Mapped[dict]=mapped_column(JSON)
    fingerprint: Mapped[str]=mapped_column(String(64))
    reviewed_state: Mapped[str]=mapped_column(String(64))
