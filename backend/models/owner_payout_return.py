"""Immutable confirmed bank credits; no pending recovery is booked here."""
from datetime import date,datetime
from decimal import Decimal
from sqlalchemy import String,Text,Date,DateTime,Numeric,ForeignKey,Boolean,JSON,CheckConstraint,func
from sqlalchemy.orm import Mapped,mapped_column
from backend.database.base import Base

class OwnerPayoutReturn(Base):
    __tablename__='owner_payout_returns'
    __table_args__=(CheckConstraint('amount>0',name='ck_payout_return_amount'),CheckConstraint('received=1',name='ck_payout_return_received'),CheckConstraint('length(trim(reason))>0 AND length(trim(bank_reference))>0',name='ck_payout_return_evidence'))
    id: Mapped[int]=mapped_column(primary_key=True)
    payout_id: Mapped[int]=mapped_column(ForeignKey('owner_payouts.id',ondelete='RESTRICT'),index=True)
    transfer_root_id: Mapped[int]=mapped_column(ForeignKey('owner_payouts.id',ondelete='RESTRICT'),index=True)
    amount: Mapped[Decimal]=mapped_column(Numeric(12,2))
    effective_date: Mapped[date]=mapped_column(Date)
    bank_reference: Mapped[str]=mapped_column(String(255))
    bank_transaction_id: Mapped[str|None]=mapped_column(String(160))
    receiving_account_hash: Mapped[str]=mapped_column(String(64))
    receiving_account_suffix: Mapped[str]=mapped_column(String(4))
    reason: Mapped[str]=mapped_column(Text)
    received: Mapped[bool]=mapped_column(Boolean)
    operator_id: Mapped[str|None]=mapped_column(String(160))
    created_at: Mapped[datetime]=mapped_column(DateTime,server_default=func.current_timestamp())
    request_key: Mapped[str]=mapped_column(String(36),unique=True)
    dedupe_key: Mapped[str]=mapped_column(String(64),unique=True)
    fingerprint: Mapped[str]=mapped_column(String(64))
    reviewed_state: Mapped[str]=mapped_column(String(64))
    impact: Mapped[dict]=mapped_column(JSON)
