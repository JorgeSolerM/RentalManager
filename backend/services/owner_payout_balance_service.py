"""One read-only source of payout balances and derived administrative states."""
from decimal import Decimal
from sqlalchemy import select
from backend.models.owner_settlement import OwnerPayout,OwnerSettlement,OwnerSettlementLine
from backend.models.owner_payout_correction import OwnerPayoutCorrectionOperation
from backend.models.payment import Payment
from backend.models.payment_allocation import PaymentAllocation
from backend.services.settlement_money import ZERO

class OwnerPayoutBalanceService:
    def summary(self,db,settlement,exclude_id=None):
        payouts=list(db.scalars(select(OwnerPayout).where(OwnerPayout.owner_id==settlement.owner_id).order_by(OwnerPayout.id)))
        ids=[p.id for p in payouts]
        operations=list(db.scalars(select(OwnerPayoutCorrectionOperation).where(OwnerPayoutCorrectionOperation.original_payout_id.in_(ids)).order_by(OwnerPayoutCorrectionOperation.created_at,OwnerPayoutCorrectionOperation.request_key))) if ids else []
        invalidated={o.original_payout_id:o for o in operations}
        states={p.id:('void' if invalidated[p.id].kind=='void' else 'replaced') if p.id in invalidated else 'posted' for p in payouts}
        effective=[p for p in payouts if states[p.id]=='posted' and p.id!=exclude_id]
        current=[p for p in payouts if p.settlement_id==settlement.id]
        paid=sum((p.amount for p in effective if p.settlement_id==settlement.id),ZERO)
        due=Decimal(settlement.snapshot['totals']['payout_due'])
        if paid>due:raise ValueError('Los pagos efectivos superan la liquidación; requiere revisión.')
        closed=list(db.scalars(select(OwnerSettlement).where(OwnerSettlement.owner_id==settlement.owner_id,OwnerSettlement.status=='closed').order_by(OwnerSettlement.id)))
        funds=sum((Decimal(s.snapshot['totals']['funds_balance'])-Decimal(s.snapshot['totals']['prior_balance']) for s in closed),ZERO)
        owner_paid=sum((p.amount for p in effective),ZERO)
        status=('Saldo a favor del gestor' if Decimal(settlement.snapshot['totals']['carry_forward'])<0 else 'Sin transferencia del gestor' if due==0 else 'Pagada' if paid==due else 'Parcialmente pagada' if paid>0 else 'Pendiente de pago')
        return dict(payouts=current,effective=[p for p in effective if p.settlement_id==settlement.id],all_payouts=payouts,operations=operations,states=states,paid=paid,due=due,remaining=due-paid,owner_funds=funds,owner_paid=owner_paid,available=max(ZERO,funds-owner_paid),status=status,closed=closed)

    def pending_returns(self,db,owner_id):
        lines=list(db.scalars(select(OwnerSettlementLine).where(OwnerSettlementLine.owner_id==owner_id)))
        consumed={r.payment_allocation_id for r in lines if r.payment_allocation_id}
        originals=list(db.scalars(select(PaymentAllocation.payment_id).where(PaymentAllocation.id.in_(consumed))))
        return list(db.scalars(select(PaymentAllocation.id).join(Payment).where(Payment.corrects_payment_id.in_(originals),Payment.lifecycle=='posted',Payment.direction=='refund',PaymentAllocation.id.not_in(consumed))))
