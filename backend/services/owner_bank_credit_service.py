"""Shared incoming bank identity across ordinary returns and incident recoveries."""
from sqlalchemy import select
from backend.models.owner_payout_return import OwnerPayoutReturn
from backend.models.owner_transfer_recovery import OwnerTransferRecovery, OwnerBankCreditIdentity
from backend.services.expense_service import fingerprint


def credit_key(account_hash, bank_id, day, amount):
    return fingerprint(['bank',account_hash,bank_id]) if bank_id else fingerprint(['possible',account_hash,str(day),str(amount)])


def validate_credit(db, *, account_hash, bank_id, day, amount, source=None):
    # Also examines legacy rows without a sidecar identity; no historical backfill.
    for model in (OwnerPayoutReturn,OwnerTransferRecovery):
        for row in db.scalars(select(model)):
            same_account=row.receiving_account_hash==account_hash
            if model is OwnerPayoutReturn:row_source=('payout',row.transfer_root_id)
            else:
                from backend.models.owner_transfer_incident import OwnerTransferIncident
                incident=db.get(OwnerTransferIncident,row.incident_id)
                row_source=('payout',incident.payout_root_id) if incident.payout_root_id else ('incident',incident.id)
            same_source=source is not None and source==row_source
            if same_account and bank_id and row.bank_transaction_id and bank_id==row.bank_transaction_id:
                raise ValueError('El abono bancario ya está registrado en devoluciones o recuperaciones.')
            if (same_account or same_source) and row.effective_date==day and row.amount==amount and (not bank_id or not row.bank_transaction_id):
                raise ValueError('Posible abono duplicado: fecha, importe y cuenta coinciden. Se necesitan identificadores bancarios distintos y verificables; cambiar la referencia no lo distingue.')
    key=credit_key(account_hash,bank_id,day,amount)
    if db.scalar(select(OwnerBankCreditIdentity.id).where(OwnerBankCreditIdentity.bank_key==key)):
        raise ValueError('Identidad bancaria ya registrada.')
    return key


def register_identity(db, row, *, recovery):
    db.add(OwnerBankCreditIdentity(recovery_id=row.id if recovery else None,return_id=None if recovery else row.id,
        bank_key=credit_key(row.receiving_account_hash,row.bank_transaction_id,row.effective_date,row.amount)))
    db.flush()
