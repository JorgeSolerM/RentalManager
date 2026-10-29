from datetime import date, datetime
from decimal import Decimal as D
from uuid import uuid4
import pytest
from sqlalchemy import select, func

from backend.models import Owner, Property, Room, Booking, BookingCharge, Payment, PaymentAllocation, PropertyOwnership
from backend.models.owner_settlement import ManagementFeeTerms, PaymentCustody, OwnerSettlement, OwnerSettlementLine, Expense, ExpensePayment, ExpenseCategory
from backend.models.fee_billing import FeeTaxConfiguration, FeeObligation, FeeCompensation
from backend.services.billing_settlement_service import BillingSettlementService
from backend.services.settlement_selection_service import SettlementSelectionService

START, END = date(2026,9,1), date(2026,10,1)


@pytest.fixture
def billing_env(db_session, monkeypatch):
    monkeypatch.setenv('INVOICING_ENABLED','true')
    monkeypatch.setenv('VERIFACTU_ENABLED','true')
    monkeypatch.setenv('VERIFACTU_SUBMISSION_ENABLED','false')
    monkeypatch.setenv('INVOICING_SYNTHETIC_DATABASE',db_session.get_bind().url.database)
    monkeypatch.setattr('backend.services.owner_settlement_service.business_today',lambda: date(2026,12,31))
    owner=Owner(legal_name='Propietario sintético',tax_id='89890001K',address_line='Calle Prueba 1',
                postal_code='03001',city='Alicante',province='Alicante',country='ES')
    db_session.add(owner);db_session.commit()
    return owner


def prop(db, owner, name='Finca prueba', percentage='20', vat='0', withholding='0', start=date(2026,1,1), end=None):
    p=Property(name=name,address='Calle Prueba',city='Elche',owner='')
    db.add(p);db.flush()
    db.add(PropertyOwnership(property_id=p.id,owner_id=owner.id,ownership_percentage=D('100'),active=True))
    terms=ManagementFeeTerms(property_id=p.id,owner_id=owner.id,effective_from=start,effective_until=end,
                            percentage=D(percentage),vat_rate=D(vat),withholding_rate=D(withholding))
    db.add(terms);db.flush();fiscal(db,terms);db.commit()
    return p,terms


def fiscal(db, terms):
    db.add(FeeTaxConfiguration(terms_id=terms.id,configuration=dict(tax_type='IVA',tax_regime='general',
        tax_treatment='subject_taxable',vat_rate=str(terms.vat_rate),withholding_mode='percentage' if terms.withholding_rate else 'none',
        withholding_rate=str(terms.withholding_rate),operation_date_policy='receipt_date')))


def receipt(db,p,amount='400',economic=START,received=date(2026,9,10)):
    room=Room(property_id=p.id,code='TEST-'+str(uuid4())[:8],active=True)
    db.add(room);db.flush()
    booking=Booking(room_id=room.id,check_in=economic,check_out=date(2027,1,1))
    db.add(booking);db.flush()
    end=date(economic.year+1,1,1) if economic.month==12 else date(economic.year,economic.month+1,1)
    charge=BookingCharge(booking_id=booking.id,type='rent',concept='Renta sintética',amount=D(amount),
        due_date=economic,service_period_start=economic,service_period_end=end,lifecycle='posted',posted_at=datetime(2026,9,1))
    payment=Payment(booking_id=booking.id,amount=D(amount),effective_date=received,method='cash',
                    direction='receipt',lifecycle='posted',posted_at=datetime(2026,9,10))
    db.add_all([charge,payment]);db.flush()
    allocation=PaymentAllocation(payment_id=payment.id,charge_id=charge.id,amount=D(amount))
    db.add_all([allocation,PaymentCustody(payment_id=payment.id,actor='manager',amount=D(amount))]);db.commit()
    return allocation


def paid_expense(db,p,amount='500'):
    category=db.scalar(select(ExpenseCategory))
    if not category:
        category=ExpenseCategory(code='test',name='Prueba',active=True);db.add(category);db.flush()
    expense=Expense(property_id=p.id,category_id=category.id,concept='Reparación sintética',expense_date=date(2026,9,10),
        base_amount=D(amount),vat_rate=D('0'),vat_amount=D('0'),withholding_rate=D('0'),withholding_amount=D('0'),
        total_amount=D(amount),borne_by='owner',lifecycle='posted')
    db.add(expense);db.flush()
    payment=ExpensePayment(expense_id=expense.id,amount=D(amount),effective_date=date(2026,9,10),
        paid_by='manager',method='bank_transfer',direction='payment',request_key=str(uuid4()),fingerprint='test')
    db.add(payment);db.commit();return payment


def drafts(db,properties,start=START,end=END,assignments=None):
    service=SettlementSelectionService()
    view=service.preview(db,start,end,[p.id for p in properties],assignments)
    assert not view['errors'] and not view['issues'],view
    return service.save_drafts(db,start,end,[p.id for p in properties],view['fingerprint'],str(uuid4()),assignments)


def test_real_homogeneous_selection_close_snapshots(db_session,billing_env):
    a,_=prop(db_session,billing_env,'A');b,_=prop(db_session,billing_env,'B')
    receipt(db_session,a);receipt(db_session,b)
    items=drafts(db_session,[a,b]);assert len(items)==1
    item=BillingSettlementService().close(db_session,items[0].id,items[0].fingerprint)
    assert item.snapshot['totals']['fees']=='160.00'
    lines=list(db_session.scalars(select(OwnerSettlementLine)))
    assert len(lines)==2 and all(l.snapshot['fiscal_snapshot']['tax_treatment']=='subject_taxable' for l in lines)
    assert db_session.scalar(select(func.count()).select_from(FeeObligation))==2
    assert db_session.scalar(select(func.sum(FeeCompensation.amount)))==160


def test_integrated_preview_uses_shared_grouping_planner(db_session, billing_env, monkeypatch):
    import backend.services.billing_settlement_service as module
    from backend.core.fee_grouping import group_fee_sources
    calls = []
    def observed(*args, **kwargs):
        result = group_fee_sources(*args, **kwargs)
        calls.append(result)
        return result
    monkeypatch.setattr(module, 'group_fee_sources', observed)
    a, _ = prop(db_session, billing_env, 'Same A')
    b, _ = prop(db_session, billing_env, 'Same B')
    receipt(db_session, a); receipt(db_session, b)
    view = SettlementSelectionService().preview(db_session, START, END, [a.id, b.id])
    assert len(calls) == 1 and not view['errors']
    assert [v['view']['group_key'] for v in view['individuals']] == [g['group_key'] for g in calls[0]['groups']]
    assert view['individuals'][0]['view']['rows'] == calls[0]['groups'][0]['sources']


def test_heterogeneous_drafts_can_close_in_proposed_order(db_session,billing_env):
    a,_=prop(db_session,billing_env,'A');b,_=prop(db_session,billing_env,'B',percentage='15')
    receipt(db_session,a);receipt(db_session,b)
    items=drafts(db_session,[a,b]);assert len(items)==2
    for item in items:
        BillingSettlementService().close(db_session,item.id,item.fingerprint)
    assert sum(D(i.snapshot['totals']['fees']) for i in items)==140


def test_historical_rate_and_ambiguous_expense(db_session,billing_env):
    p,old=prop(db_session,billing_env,percentage='15',end=START)
    new=ManagementFeeTerms(property_id=p.id,owner_id=billing_env.id,effective_from=START,percentage=D('20'),vat_rate=D('0'),withholding_rate=D('0'))
    db_session.add(new);db_session.flush();fiscal(db_session,new);db_session.commit()
    receipt(db_session,p,economic=date(2026,8,1));receipt(db_session,p)
    paid_expense(db_session,p)
    service=SettlementSelectionService();view=service.preview(db_session,START,END,[p.id])
    assert len(view['individuals'])==2 and len(view['issues'])==1
    assert sorted(v['view']['totals']['fees'] for v in view['individuals'])==['60.00','80.00']
    issue=view['issues'][0];assignment={issue['field']:issue['candidates'][0]['key']}
    items=drafts(db_session,[p],assignments=assignment)
    for item in items: BillingSettlementService().close(db_session,item.id,item.fingerprint)
    assert db_session.scalar(select(func.count()).select_from(OwnerSettlementLine).where(OwnerSettlementLine.kind=='expense'))==1


def test_insufficient_then_new_cash_recovers_original_obligations(db_session,billing_env):
    p,_=prop(db_session,billing_env);receipt(db_session,p,'300');paid_expense(db_session,p)
    first=drafts(db_session,[p])[0];BillingSettlementService().close(db_session,first.id,first.fingerprint)
    assert first.snapshot['totals']['pending_expense']=='200.00'
    assert first.snapshot['totals']['pending_fee']=='60.00'
    assert first.snapshot['totals']['payout_due']=='0.00'
    # New receipt generates its own fee too (100), separately from old 260.
    receipt(db_session,p,'500',economic=date(2026,10,1),received=date(2026,10,10))
    second=drafts(db_session,[p],date(2026,10,1),date(2026,11,1))[0]
    BillingSettlementService().close(db_session,second.id,second.fingerprint)
    assert second.snapshot['totals']['prior_balance']=='-260.00'
    assert second.snapshot['totals']['payout_due']=='140.00'
    assert first.snapshot['totals']['manager_credit']=='260.00'


def test_prior_debt_partial_across_groups_and_stale_close(db_session,billing_env):
    p,_=prop(db_session,billing_env);receipt(db_session,p,'300');paid_expense(db_session,p)
    first=drafts(db_session,[p])[0];BillingSettlementService().close(db_session,first.id,first.fingerprint)
    # Two new groups: 200 then 500 (ordering is stable by receipt date).
    a,_=prop(db_session,billing_env,'Second 0%',percentage='0')
    b,_=prop(db_session,billing_env,'Third 10%',percentage='10')
    receipt(db_session,a,'200',received=date(2026,10,2));receipt(db_session,b,'500',received=date(2026,10,3))
    items=drafts(db_session,[a,b],date(2026,10,1),date(2026,11,1))
    assert [i.snapshot['totals']['prior_balance'] for i in items]==['-200.00','-60.00']
    with pytest.raises(ValueError,match='desactualizados'):
        BillingSettlementService().close(db_session,items[1].id,items[1].fingerprint)
    for item in items:BillingSettlementService().close(db_session,item.id,item.fingerprint)
    assert items[0].snapshot['totals']['payout_due']=='0.00'
    assert items[1].snapshot['totals']['payout_due']=='390.00' # 500 - old 60 - new fee 50


def test_explicit_operation_date_ui_and_homogeneous_terms_content(client,db_session,billing_env):
    p,t=prop(db_session,billing_env);allocation=receipt(db_session,p)
    cfg=db_session.scalar(select(FeeTaxConfiguration).where(FeeTaxConfiguration.terms_id==t.id))
    cfg.configuration={**cfg.configuration,'operation_date_policy':'explicit'};db_session.commit()
    response=client.post('/settlements/preview',data={'month':'2026-09','property_id':str(p.id)})
    assert response.status_code==200 and f'name="operation_income:{allocation.id}"' in response.text
    op={f'income:{allocation.id}':'2026-09-12'}
    svc=SettlementSelectionService();v=svc.preview(db_session,START,END,[p.id],operation_dates=op)
    assert not v['errors']
    items=svc.save_drafts(db_session,START,END,[p.id],v['fingerprint'],str(uuid4()),operation_dates=op)
    BillingSettlementService().close(db_session,items[0].id,items[0].fingerprint)
    assert items[0].snapshot['rows'][0]['fiscal_snapshot']['operation_date']=='2026-09-12'
