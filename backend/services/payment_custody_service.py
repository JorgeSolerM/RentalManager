"""Custody for NEW ordinary receipts; never backfills or changes old receipts."""
from sqlalchemy import select

from backend.models.owner_settlement import PaymentCustody


def record_manager_receipt(db, payment):
    """Participates in the caller's transaction; does not commit independently."""
    if payment.direction != 'receipt' or payment.lifecycle != 'posted':
        return
    db.flush()
    if db.scalar(select(PaymentCustody.id).where(PaymentCustody.payment_id == payment.id)):
        raise ValueError('El cobro ya tiene custodia registrada; no se sustituye automáticamente.')
    db.add(PaymentCustody(payment_id=payment.id, actor='manager', owner_id=None,
                         amount=payment.amount))
