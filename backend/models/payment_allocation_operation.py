from datetime import datetime
from decimal import Decimal
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, JSON, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column
from backend.database.base import Base


class PaymentAllocationOperation(Base):
    """Append-only receipt of a reviewed assignment; does not create a Payment."""
    __tablename__ = 'payment_allocation_operations'
    __table_args__ = (CheckConstraint('amount > 0', name='ck_allocation_operation_positive'),)
    request_key: Mapped[str] = mapped_column(String(36), primary_key=True)
    payment_id: Mapped[int] = mapped_column(ForeignKey('payments.id', ondelete='RESTRICT'), index=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    reviewed_state: Mapped[str] = mapped_column(String(64))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    changes: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
