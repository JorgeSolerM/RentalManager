from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from backend.database.base import Base


class PaymentRegistration(Base):
    """Idempotency receipt for a reviewed manual payment, not a SEPA entity."""
    __tablename__ = 'payment_registrations'
    request_key: Mapped[str] = mapped_column(String(36), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    payment_id: Mapped[int] = mapped_column(ForeignKey('payments.id', ondelete='RESTRICT'), unique=True)
