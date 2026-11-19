from datetime import datetime
from sqlalchemy import String, Text, DateTime, ForeignKey, JSON, Boolean, CheckConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from backend.database.base import Base

class AuditFields:
    request_key: Mapped[str] = mapped_column(String(36), primary_key=True)
    expense_id: Mapped[int] = mapped_column(ForeignKey('expenses.id', ondelete='RESTRICT'), index=True)
    reason: Mapped[str] = mapped_column(Text)
    before_state: Mapped[dict] = mapped_column(JSON)
    after_state: Mapped[dict] = mapped_column(JSON)
    impact: Mapped[dict] = mapped_column(JSON)
    fingerprint: Mapped[str] = mapped_column(String(64))
    reviewed_state: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())

class ExpensePaymentVoidOperation(AuditFields, Base):
    __tablename__ = 'expense_payment_void_operations'
    __table_args__ = (CheckConstraint('no_money_moved = 1', name='ck_expense_void_no_money'),
                     CheckConstraint('length(trim(reason)) > 0', name='ck_expense_payment_void_reason'))
    payment_id: Mapped[int] = mapped_column(ForeignKey('expense_payments.id', ondelete='RESTRICT'), unique=True)
    no_money_moved: Mapped[bool] = mapped_column(Boolean)

class ExpenseCorrectionOperation(AuditFields, Base):
    __tablename__ = 'expense_correction_operations'
    __table_args__ = (CheckConstraint("kind IN ('correct','void')", name='ck_expense_correction_kind'),
                     CheckConstraint('length(trim(reason)) > 0', name='ck_expense_correction_reason'))
    kind: Mapped[str] = mapped_column(String(12))
