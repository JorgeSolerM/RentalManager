from datetime import date, datetime
from decimal import Decimal as D
from uuid import uuid4

import pytest
from sqlalchemy import select, func

from backend.models import Owner, Property, Room, Booking, BookingCharge, Payment, PaymentAllocation, PropertyOwnership
from backend.models.owner_bank_account import OwnerBankAccount
from backend.models.owner_settlement import ManagementFeeTerms, OwnerSettlement, OwnerSettlementLine, OwnerPayout
from backend.services.owner_settlement_service import OwnerSettlementService

service = OwnerSettlementService()
from backend.services.settlement_selection_service import SettlementSelectionService
selection_service = SettlementSelectionService()


@pytest.fixture
def sample(db_session, monkeypatch):
    monkeypatch.setattr("backend.services.owner_settlement_service.business_today", lambda: date(2026, 10, 31))
    p = Property(name="Finca sintética", address="Calle prueba", city="Elche", owner="")
    a, b = Owner(legal_name="Propietario sintético A"), Owner(legal_name="Propietario sintético B")
    db_session.add_all([p, a, b]); db_session.flush()
    room = Room(property_id=p.id, code="TEST-01", active=True)
    db_session.add(room); db_session.flush()
    booking = Booking(room_id=room.id, check_in=date(2026, 9, 1), check_out=date(2026, 10, 1))
    db_session.add(booking); db_session.flush()
    charge = BookingCharge(booking_id=booking.id, type="rent", concept="Renta sintética septiembre",
        amount=D("500"), due_date=date(2026, 9, 1), service_period_start=date(2026, 9, 1),
        service_period_end=date(2026, 10, 1), lifecycle="posted", posted_at=datetime(2026, 9, 1))
    payment = Payment(booking_id=booking.id, amount=D("500"), effective_date=date(2026, 9, 15),
        direction="receipt", method="bank_transfer", lifecycle="posted", posted_at=datetime(2026, 9, 15))
    db_session.add_all([charge, payment]); db_session.flush()
    allocation = PaymentAllocation(payment_id=payment.id, charge_id=charge.id, amount=D("500"))
    db_session.add(allocation)
    for owner in (a, b):
        db_session.add(PropertyOwnership(property_id=p.id, owner_id=owner.id, ownership_percentage=D("50"), active=True))
        db_session.add(ManagementFeeTerms(property_id=p.id, owner_id=owner.id, effective_from=date(2026, 1, 1),
            percentage=D("20"), vat_rate=D("0"), withholding_rate=D("0")))
    db_session.commit()
    service.set_custody(db_session, payment.id, actor="manager")
    return dict(property=p, a=a, b=b, booking=booking, payment=payment, allocation=allocation, charge=charge)


def preview(db, sample, owner="a", excluded=()):
    return service.preview(db, sample[owner].id, date(2026, 9, 1), date(2026, 10, 1), [sample["property"].id], excluded)


def draft(db, sample, owner="a", excluded=()):
    view = preview(db, sample, owner, excluded)
    assert view["errors"] == []
    return service.save_draft(db, owner_id=sample[owner].id, start=date(2026, 9, 1), end=date(2026, 10, 1),
        property_ids=[sample["property"].id], excluded=list(excluded), expected=view["fingerprint"], request_key=str(uuid4()))


def test_individual_close_and_no_automatic_payout(db_session, sample):
    a = draft(db_session, sample)
    service.close(db_session, a.id, a.fingerprint)
    assert a.snapshot["totals"]["payout_due"] == "200.00"
    assert db_session.scalar(select(func.count()).select_from(OwnerPayout)) == 0
    b = draft(db_session, sample, "b")
    service.close(db_session, b.id, b.fingerprint)
    assert b.snapshot["totals"]["income"] == "250.00"
    assert db_session.scalar(select(func.count()).select_from(OwnerSettlementLine)) == 2
    service.close(db_session, a.id, a.fingerprint)
    assert db_session.scalar(select(func.count()).select_from(OwnerSettlementLine)) == 2
    assert preview(db_session, sample)["rows"] == []


def test_other_owner_custody_never_blocks_close(db_session, sample):
    service.set_custody(db_session, sample["payment"].id, actor="owner", owner_id=sample["a"].id)
    for owner, direct, difference in (("a", "500.00", "250.00"), ("b", "0.00", "-250.00")):
        item = draft(db_session, sample, owner)
        service.close(db_session, item.id, item.fingerprint)
        assert item.status == "closed"
        assert item.snapshot["totals"]["directly_received"] == direct
        assert item.snapshot["totals"]["inter_owner_difference"] == difference
        assert item.snapshot["totals"]["payout_due"] == "0.00"


def test_preview_does_not_write_and_exclusion_does_not_consume(db_session, sample):
    key = f"income:{sample['allocation'].id}"
    view = preview(db_session, sample, excluded=[key])
    assert view["totals"]["income"] == "0.00"
    assert db_session.scalar(select(func.count()).select_from(OwnerSettlement)) == 0
    assert preview(db_session, sample)["totals"]["income"] == "250.00"


def test_stale_custody_prevents_close(db_session, sample):
    item = draft(db_session, sample)
    service.set_custody(db_session, sample["payment"].id, actor="owner", owner_id=sample["a"].id)
    with pytest.raises(ValueError, match="desactualizados"):
        service.close(db_session, item.id, item.fingerprint)
    assert db_session.scalar(select(func.count()).select_from(OwnerSettlementLine)) == 0


def refund(db, sample):
    p = Payment(booking_id=sample["booking"].id, amount=D("500"), effective_date=date(2026, 9, 20),
        direction="refund", method="sepa_direct_debit", lifecycle="posted", posted_at=datetime(2026, 9, 20),
        corrects_payment_id=sample["payment"].id)
    db.add(p); db.flush()
    db.add(PaymentAllocation(payment_id=p.id, charge_id=sample["charge"].id, amount=D("500")))
    db.commit()


def test_refund_before_closing_has_zero_net_and_fee(db_session, sample):
    refund(db_session, sample)
    view = preview(db_session, sample)
    assert view["errors"] == []
    assert view["totals"]["income"] == view["totals"]["fees"] == "0.00"


def test_refund_after_closing_preserves_snapshot_and_reverses_fee(db_session, sample):
    original = draft(db_session, sample)
    service.close(db_session, original.id, original.fingerprint)
    snapshot = original.snapshot
    refund(db_session, sample)
    view = preview(db_session, sample)
    assert view["totals"]["income"] == "-250.00"
    assert view["totals"]["fees"] == "-50.00"
    assert view["totals"]["carry_forward"] == "-200.00"
    db_session.refresh(original)
    assert original.snapshot == snapshot


def test_incomplete_ownership_blocks_close(db_session, sample):
    ownership = db_session.scalar(select(PropertyOwnership).where(PropertyOwnership.owner_id == sample["a"].id))
    ownership.ownership_percentage = D("40")
    db_session.commit()
    view = preview(db_session, sample)
    assert view["errors"]


def test_payout_partial_full_idempotent_and_snapshot(db_session, sample):
    item = draft(db_session, sample)
    service.close(db_session, item.id, item.fingerprint)
    account = OwnerBankAccount(owner_id=sample["a"].id, account_holder_name="Titular sintético",
        iban="ES9121000418450200051332", active=True, receives_settlements=True)
    db_session.add(account); db_session.commit()
    def payout(amount, key):
        return service.payout(db_session, item.id, amount=amount, effective_date=date(2026, 9, 30),
                             bank_account_id=account.id, method="bank_transfer", request_key=key)
    key = str(uuid4())
    first = payout("100", key)
    assert payout("100", key).id == first.id
    payout("100", str(uuid4()))
    with pytest.raises(ValueError, match="supera"):
        payout("0.01", str(uuid4()))
    account.iban = "GB82WEST12345698765432"
    db_session.commit(); db_session.refresh(first)
    assert first.account_snapshot["iban"] == "ES9121000418450200051332"


def test_delayed_receipt_uses_economic_period_version(db_session, sample):
    for owner in (sample['a'], sample['b']):
        service.add_terms(db_session, property_id=sample['property'].id, owner_id=owner.id,
            effective_from=date(2026, 10, 1), effective_until=None, percentage='30', vat_rate='0', withholding_rate='0')
    sample['payment'].effective_date = date(2026, 10, 15)
    db_session.commit()
    view = service.preview(db_session, sample['a'].id, date(2026, 10, 1), date(2026, 11, 1), [sample['property'].id])
    assert view['errors'] == []
    assert view['totals']['fees'] == '50.00'


def test_close_rolls_back_all_consumptions(db_session, sample, monkeypatch):
    item = draft(db_session, sample)
    original = db_session.add
    def fail(value, *args, **kwargs):
        if isinstance(value, OwnerSettlementLine):
            raise RuntimeError('synthetic failure')
        return original(value, *args, **kwargs)
    monkeypatch.setattr(db_session, 'add', fail)
    with pytest.raises(RuntimeError):
        service.close(db_session, item.id, item.fingerprint)
    db_session.refresh(item)
    assert item.status == 'draft'
    assert db_session.scalar(select(func.count()).select_from(OwnerSettlementLine)) == 0


def test_concurrent_individual_close_consumes_only_once(db_session, sample):
    from concurrent.futures import ThreadPoolExecutor
    from sqlalchemy.orm import Session
    one, two = draft(db_session, sample), draft(db_session, sample)
    targets = [(one.id, one.fingerprint), (two.id, two.fingerprint)]
    engine = db_session.bind
    db_session.rollback()
    def close_in_session(target):
        with Session(engine) as db:
            try:
                service.close(db, *target)
                return True
            except ValueError:
                return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(close_in_session, targets)) == [False, True]
    assert db_session.scalar(select(func.count()).select_from(OwnerSettlementLine)) == 1


def test_expenses_partial_owner_paid_and_fee_base(db_session, sample, monkeypatch):
    from backend.models.owner_settlement import ExpenseCategory
    from backend.services.expense_service import ExpenseService
    monkeypatch.setattr('backend.services.expense_service.business_today', lambda: date(2026, 10, 31))
    category = ExpenseCategory(code='synthetic', name='Prueba', active=True)
    db_session.add(category); db_session.commit()
    es = ExpenseService()
    expense = es.create(db_session, property_id=sample['property'].id, category_id=category.id,
        expense_date=date(2026, 9, 1), concept='Prueba', base_amount='300', vat_rate='0', withholding_rate='0')
    assert preview(db_session, sample)['totals']['expenses'] == '0.00'
    payment = es.pay(db_session, expense.id, effective_date=date(2026, 9, 10), amount='100',
        paid_by='owner', paid_by_owner_id=sample['a'].id, request_key=str(uuid4()))
    view = preview(db_session, sample)
    assert view['totals']['expenses'] == '50.00'
    assert view['totals']['fees'] == '50.00'
    assert view['totals']['payout_due'] == '200.00'
    item = draft(db_session, sample)
    service.close(db_session, item.id, item.fingerprint)
    assert es.balance(db_session, expense.id).settled == D('50')
    assert es.balance(db_session, expense.id).available == D('50')
    item_b = draft(db_session, sample, 'b')
    service.close(db_session, item_b.id, item_b.fingerprint)
    assert es.balance(db_session, expense.id).available == D('0')
    es.pay(db_session, expense.id, effective_date=date(2026, 9, 20), amount='100',
        paid_by='owner', paid_by_owner_id=sample['a'].id, corrects_id=payment.id, request_key=str(uuid4()))
    assert preview(db_session, sample)['totals']['expenses'] == '-50.00'


def test_negative_balance_is_carried_only_once(db_session, sample):
    first = draft(db_session, sample)
    service.close(db_session, first.id, first.fingerprint)
    refund(db_session, sample)
    negative = draft(db_session, sample)
    service.close(db_session, negative.id, negative.fingerprint)
    view = preview(db_session, sample)
    assert view['totals']['prior_balance'] == '-200.00'
    carry = draft(db_session, sample)
    service.close(db_session, carry.id, carry.fingerprint)
    after = preview(db_session, sample)
    assert after['totals']['prior_balance'] == '-200.00'
    assert len(after['rows']) == 1


@pytest.mark.parametrize('fee,debt,next_gross,net_payout', [('0','200','1400','500'), ('20','260','1750','440')])
def test_manager_advance_then_compensation_and_payout(db_session, sample, client, tmp_path, monkeypatch, fee, debt, next_gross, net_payout):
    from copy import deepcopy
    from backend.services.expense_service import ExpenseService
    from backend.models.owner_settlement import ExpenseCategory
    from backend.services.settlement_document_service import SettlementDocumentService
    from pypdf import PdfReader
    monkeypatch.setattr('backend.services.expense_service.business_today',lambda:date(2026,10,31))
    # Each co-owner receives 300; the 500 expense belongs only to A.
    sample['payment'].amount=sample['allocation'].amount=sample['charge'].amount=D('600')
    for terms in db_session.scalars(select(ManagementFeeTerms)):
        terms.percentage=D(fee)
    db_session.commit()
    service.set_custody(db_session,sample['payment'].id,actor='manager')
    category=ExpenseCategory(code='advance-test',name='Reparación sintética',active=True)
    db_session.add(category);db_session.commit()
    es=ExpenseService()
    expense=es.create(db_session,property_id=sample['property'].id,owner_id=sample['a'].id,
        category_id=category.id,expense_date=date(2026,9,1),concept='Reparación adelantada por gestor',
        base_amount='500',vat_rate='0',withholding_rate='0')
    es.pay(db_session,expense.id,effective_date=date(2026,9,10),amount='500',paid_by='manager',request_key=str(uuid4()))
    negative=draft(db_session,sample);service.close(db_session,negative.id,negative.fingerprint)
    assert negative.snapshot['totals']['economic_balance']==str(-D(debt).quantize(D('.01')))
    assert negative.snapshot['totals']['payout_due']=='0.00'
    assert negative.snapshot['totals']['manager_credit']==str(D(debt).quantize(D('.01')))
    original=deepcopy(negative.snapshot)
    assert preview(db_session,sample,'b')['totals']['prior_balance']=='0.00'
    assert preview(db_session,sample,'b')['totals']['economic_balance']==str((D('300')*(1-D(fee)/100)).quantize(D('.01')))
    assert 'Saldo a favor del gestor' in client.get(f'/settlements/{negative.id}').text
    assert 'Saldo a favor del gestor' in client.get('/settlements').text
    docs=SettlementDocumentService(tmp_path/'documents')
    docs.generate(db_session,negative.id)
    text='\n'.join(p.extract_text() for p in PdfReader(docs.download(db_session,negative.id,1)[1]).pages)
    assert 'SALDO A FAVOR DEL GESTOR' in text and f'-{debt},00' in text
    assert 'PENDIENTE DE TRANSFERIR' not in text
    with pytest.raises(ValueError):
        service.payout(db_session,negative.id,amount='-200',effective_date=date(2026,9,30),bank_account_id=1,
                       method='bank_transfer',request_key=str(uuid4()))
    # New receipt gives each owner 700 after the applicable fee.
    charge=BookingCharge(booking_id=sample['booking'].id,type='rent',concept='Renta siguiente sintética',
        amount=D(next_gross),due_date=date(2026,10,1),service_period_start=date(2026,10,1),
        service_period_end=date(2026,11,1),lifecycle='posted',posted_at=datetime(2026,10,1))
    payment=Payment(booking_id=sample['booking'].id,amount=D(next_gross),effective_date=date(2026,10,5),
        direction='receipt',method='bank_transfer',lifecycle='posted',posted_at=datetime(2026,10,5))
    db_session.add_all([charge,payment]);db_session.flush()
    db_session.add(PaymentAllocation(payment_id=payment.id,charge_id=charge.id,amount=D(next_gross)))
    db_session.commit();service.set_custody(db_session,payment.id,actor='manager')
    args=(sample['a'].id,date(2026,10,1),date(2026,11,1),[sample['property'].id])
    view=service.preview(db_session,*args)
    assert view['totals']['period_balance']=='700.00'
    assert view['totals']['prior_balance']==str(-D(debt).quantize(D('.01')))
    assert view['totals']['economic_balance']==view['totals']['payout_due']==str(D(net_payout).quantize(D('.01')))
    def save():
        return service.save_draft(db_session,owner_id=args[0],start=args[1],end=args[2],property_ids=args[3],
            excluded=[],expected=view['fingerprint'],request_key=str(uuid4()))
    next_item=save();stale=save()
    service.close(db_session,next_item.id,next_item.fingerprint)
    with pytest.raises(ValueError,match='desactualizados'):
        service.close(db_session,stale.id,stale.fingerprint)
    assert service.preview(db_session,*args)['totals']['prior_balance']=='0.00'
    assert db_session.scalar(select(func.count()).select_from(OwnerSettlementLine).where(
        OwnerSettlementLine.prior_settlement_id==negative.id))==1
    db_session.refresh(negative);assert negative.snapshot==original
    docs.generate(db_session,next_item.id)
    text='\n'.join(p.extract_text() for p in PdfReader(docs.download(db_session,next_item.id,1)[1]).pages)
    assert 'Saldo anterior / compensación' in text and '700,00' in text and f'{net_payout},00' in text
    account=OwnerBankAccount(owner_id=sample['a'].id,account_holder_name='Titular sintético',
        iban='ES9121000418450200051332',active=True,receives_settlements=True)
    db_session.add(account);db_session.commit()
    for amount in ('200',str(D(net_payout)-D('200'))):
        service.payout(db_session,next_item.id,amount=amount,effective_date=date(2026,10,30),
            bank_account_id=account.id,method='bank_transfer',request_key=str(uuid4()))
    with pytest.raises(ValueError,match='supera'):
        service.payout(db_session,next_item.id,amount='.01',effective_date=date(2026,10,30),
            bank_account_id=account.id,method='bank_transfer',request_key=str(uuid4()))


def test_public_app_has_no_owner_economy_routes():
    from backend.public.app_factory import create_public_app
    from fastapi.testclient import TestClient
    with TestClient(create_public_app()) as public:
        for path in ('/expenses', '/settlements', '/settlements/1', '/expenses/1'):
            assert public.get(path).status_code == 404


def test_admin_routes_render(client, db_session, sample):
    item = draft(db_session, sample)
    for path in ('/expenses','/expenses/new','/settlements','/settlements/new','/settlements/terms',
                 '/settlements/custody',f'/settlements/{item.id}'):
        response = client.get(path)
        assert response.status_code == 200
    assert 'Resultado económico' in client.get(f'/settlements/{item.id}').text
    assert 'Cerrar liquidación' in client.get(f'/settlements/{item.id}').text


def test_ownership_version_preserves_closed_period(db_session, sample):
    item = draft(db_session, sample)
    service.close(db_session, item.id, item.fingerprint)
    service.version_ownership(db_session, sample['property'].id, date(2026, 10, 1),
                              [(sample['a'].id, '60'), (sample['b'].id, '40')])
    past = service.ownership(db_session, sample['property'].id, date(2026, 9, 1), date(2026, 10, 1))
    current = service.ownership(db_session, sample['property'].id, date(2026, 10, 1))
    assert sorted(r.ownership_percentage for r in past) == [D('50'), D('50')]
    assert sorted(r.ownership_percentage for r in current) == [D('40'), D('60')]
    assert preview(db_session, sample, 'b')['totals']['income'] == '250.00'


def test_property_selection_coproperty_read_only_and_idempotent(db_session, sample):
    args = (date(2026, 9, 1), date(2026, 10, 1), [sample['property'].id])
    view = selection_service.preview(db_session, *args)
    assert not view['errors']
    assert len(view['individuals']) == 2
    assert db_session.scalar(select(func.count()).select_from(OwnerSettlement)) == 0
    key = str(uuid4())
    items = selection_service.save_drafts(db_session, *args, view['fingerprint'], key)
    assert len(items) == 2
    assert len(selection_service.save_drafts(db_session, *args, view['fingerprint'], key)) == 2
    service.close(db_session, items[0].id, items[0].fingerprint)
    assert len(selection_service.save_drafts(db_session, *args, view['fingerprint'], key)) == 2
    service.close(db_session, items[1].id, items[1].fingerprint)
    assert db_session.scalar(select(func.count()).select_from(OwnerSettlementLine)) == 2


def test_property_selection_single_owner(db_session, sample):
    rows = list(db_session.scalars(select(PropertyOwnership)))
    for row in rows:
        if row.owner_id == sample['b'].id:
            db_session.delete(row)
        else:
            row.ownership_percentage = D('100')
    db_session.commit()
    view = selection_service.preview(db_session, date(2026,9,1),date(2026,10,1),[sample['property'].id])
    assert len(view['individuals']) == 1
    assert view['individuals'][0]['view']['totals']['income'] == '500.00'


@pytest.mark.parametrize('defect', ['no_ownership', 'incomplete', 'no_fees'])
def test_property_selection_review_blocks_atomic_creation(db_session, sample, defect):
    if defect == 'no_fees':
        for row in db_session.scalars(select(ManagementFeeTerms)):
            db_session.delete(row)
    else:
        for row in db_session.scalars(select(PropertyOwnership)):
            if defect == 'no_ownership':
                db_session.delete(row)
            else:
                row.ownership_percentage = D('20')
    db_session.commit()
    args = (date(2026,9,1),date(2026,10,1),[sample['property'].id])
    view = selection_service.preview(db_session,*args)
    assert view['groups'][0]['state'] == 'review'
    with pytest.raises(ValueError):
        selection_service.save_drafts(db_session,*args,view['fingerprint'],str(uuid4()))
    assert db_session.scalar(select(func.count()).select_from(OwnerSettlement)) == 0


def test_property_selection_multiple_and_no_movements(db_session, sample):
    other = Property(name='Finca vacía sintética',address='Prueba',city='Elche',owner='')
    db_session.add(other); db_session.flush()
    db_session.add(PropertyOwnership(property_id=other.id,owner_id=sample['a'].id,ownership_percentage=D('100'),active=True))
    db_session.commit()
    view = selection_service.preview(db_session,date(2026,9,1),date(2026,10,1),[other.id,sample['property'].id])
    assert len(view['groups']) == 2
    assert next(g for g in view['groups'] if g['id'] == other.id)['state'] == 'empty'
    assert len(view['individuals']) == 2


def test_property_selection_multiple_fincas_same_owner(db_session, sample):
    p = Property(name='Segunda finca sintética', address='Prueba',city='Elche',owner='')
    db_session.add(p); db_session.flush()
    db_session.add(PropertyOwnership(property_id=p.id, owner_id=sample['a'].id,ownership_percentage=D('100'),active=True))
    db_session.add(ManagementFeeTerms(property_id=p.id,owner_id=sample['a'].id,effective_from=date(2026,1,1),percentage=D('20'),vat_rate=D('0'),withholding_rate=D('0')))
    room = Room(property_id=p.id,code='TEST-SECOND',active=True)
    db_session.add(room); db_session.flush()
    booking = Booking(room_id=room.id,check_in=date(2026,9,1),check_out=date(2026,10,1))
    db_session.add(booking); db_session.flush()
    charge = BookingCharge(booking_id=booking.id,type='rent',concept='Otra renta',amount=D('100'),due_date=date(2026,9,1),service_period_start=date(2026,9,1),service_period_end=date(2026,10,1),lifecycle='posted')
    payment = Payment(booking_id=booking.id,amount=D('100'),effective_date=date(2026,9,15),direction='receipt',method='bank_transfer',lifecycle='posted')
    charge.posted_at = datetime(2026,9,1)
    payment.posted_at = datetime(2026,9,15)
    db_session.add_all([charge,payment]); db_session.flush()
    db_session.add(PaymentAllocation(payment_id=payment.id,charge_id=charge.id,amount=D('100')))
    db_session.commit()
    service.set_custody(db_session,payment.id,actor='manager')
    args=(date(2026,9,1),date(2026,10,1),[sample['property'].id,p.id])
    view=selection_service.preview(db_session,*args)
    assert not view['errors']
    assert len(view['individuals']) == 2
    owner_a=next(e['view'] for e in view['individuals'] if e['view']['owner_id']==sample['a'].id)
    assert len(owner_a['property_ids']) == 2
    assert owner_a['totals']['income'] == '350.00'
    assert len(selection_service.save_drafts(db_session,*args,view['fingerprint'],str(uuid4()))) == 2


def test_property_selection_atomic_rollback(db_session, sample):
    from sqlalchemy import event
    args=(date(2026,9,1),date(2026,10,1),[sample['property'].id])
    view=selection_service.preview(db_session,*args)
    seen=[]
    def fail_second(mapper, connection, target):
        seen.append(target.owner_id)
        if len(seen)==2:
            raise RuntimeError('synthetic failure')
    event.listen(OwnerSettlement,'before_insert',fail_second)
    try:
        with pytest.raises(RuntimeError,match='synthetic failure'):
            selection_service.save_drafts(db_session,*args,view['fingerprint'],str(uuid4()))
    finally:
        event.remove(OwnerSettlement,'before_insert',fail_second)
    assert db_session.scalar(select(func.count()).select_from(OwnerSettlement)) == 0


def test_property_selection_stale(db_session, sample):
    args = (date(2026,9,1),date(2026,10,1),[sample['property'].id])
    view = selection_service.preview(db_session,*args)
    service.set_custody(db_session,sample['payment'].id,actor='owner',owner_id=sample['a'].id)
    with pytest.raises(ValueError,match='cambiado'):
        selection_service.save_drafts(db_session,*args,view['fingerprint'],str(uuid4()))
    assert db_session.scalar(select(func.count()).select_from(OwnerSettlement)) == 0


def test_property_selection_routes_no_owner_required(client, db_session, sample):
    import re
    response = client.get('/settlements/new?month=2026-09')
    assert response.status_code == 200
    assert not re.search(r'<select[^>]*name="owner_id"', response.text)
    assert re.search(r'<input[^>]*name="property_id"', response.text)
    response = client.post('/settlements/preview',data={'month':'2026-09','property_id':str(sample['property'].id),'owner_id':'999999'})
    assert '2 liquidaciones individuales previstas' in response.text
    assert 'Guardar 2 borradores' in response.text
    assert db_session.scalar(select(func.count()).select_from(OwnerSettlement)) == 0


def test_pdf_closed_only_frozen_individual_and_hash(db_session, sample, tmp_path):
    from backend.services.settlement_document_service import SettlementDocumentService
    from pypdf import PdfReader
    from hashlib import sha256
    documents = SettlementDocumentService(tmp_path/'documents')
    item = draft(db_session, sample)
    with pytest.raises(ValueError,match='cerradas'):
        documents.generate(db_session,item.id)
    service.close(db_session,item.id,item.fingerprint)
    old_name = sample['a'].name
    sample['a'].legal_name='Nombre posterior'
    sample['property'].name='Finca posterior'
    sample['charge'].amount=D('999')
    db_session.commit()
    artifact = documents.generate(db_session,item.id)
    meta,path = documents.download(db_session,item.id,1)
    text='\n'.join(p.extract_text() for p in PdfReader(path).pages)
    assert old_name in text and 'Nombre posterior' not in text and 'Finca posterior' not in text
    assert sample['b'].name not in text
    assert '250,00' in text and '200,00' in text and '999,00' not in text
    assert sha256(path.read_bytes()).hexdigest()==artifact['sha256']
    assert documents.generate(db_session,item.id)==artifact
    assert meta['filename'].startswith(f'liquidacion-{item.id}-v1-')
    path.write_bytes(b'corrupt test file')
    with pytest.raises(ValueError,match='Integridad'):
        documents.download(db_session,item.id,1)


def test_pdf_payout_creates_version_without_overwriting(db_session, sample, tmp_path):
    from backend.services.settlement_document_service import SettlementDocumentService
    from pypdf import PdfReader
    docs=SettlementDocumentService(tmp_path/'documents')
    item=draft(db_session,sample)
    service.close(db_session,item.id,item.fingerprint)
    first=docs.generate(db_session,item.id)
    account=OwnerBankAccount(owner_id=sample['a'].id,account_holder_name='Titular sintético',iban='ES9121000418450200051332',active=True,receives_settlements=True)
    db_session.add(account);db_session.commit()
    service.payout(db_session,item.id,amount='50',effective_date=date(2026,9,20),bank_account_id=account.id,method='bank_transfer',request_key=str(uuid4()))
    second=docs.generate(db_session,item.id)
    assert second['version']==2
    assert docs.download(db_session,item.id,1)[0]['sha256']==first['sha256']
    text='\n'.join(p.extract_text() for p in PdfReader(docs.download(db_session,item.id,2)[1]).pages)
    assert '150,00' in text and '50,00' in text and '**** 1332' in text
    assert account.iban not in text


def test_pdf_renderer_version_preserves_original(db_session, sample, tmp_path, monkeypatch):
    from backend.services.settlement_document_service import SettlementDocumentService
    import backend.services.settlement_pdf as renderer
    docs=SettlementDocumentService(tmp_path/'documents')
    item=draft(db_session,sample)
    service.close(db_session,item.id,item.fingerprint)
    monkeypatch.setattr(renderer,'RENDERER_VERSION',1)
    first=docs.generate(db_session,item.id)
    original=docs.download(db_session,item.id,1)[1].read_bytes()
    monkeypatch.setattr(renderer,'RENDERER_VERSION',2)
    second=docs.generate(db_session,item.id)
    assert second['version']==2 and second['renderer_version']==2
    assert first['source_sha256']==second['source_sha256']
    assert docs.download(db_session,item.id,1)[1].read_bytes()==original
    assert docs.generate(db_session,item.id)==second


def test_pdf_admin_download_and_public_not_exposed(client, db_session, sample):
    item=draft(db_session,sample)
    assert 'Descargar PDF de liquidación' not in client.get(f'/settlements/{item.id}').text
    service.close(db_session,item.id,item.fingerprint)
    assert 'Descargar PDF de liquidación' in client.get(f'/settlements/{item.id}').text
    response=client.post(f'/settlements/{item.id}/documents',follow_redirects=False)
    assert response.status_code==303
    result=client.get(response.headers['location'])
    assert result.status_code==200 and result.content.startswith(b'%PDF-')
    assert result.headers['cache-control']=='private, no-store'
    assert 'attachment' in result.headers['content-disposition']
    from backend.public.app_factory import create_public_app
    from fastapi.testclient import TestClient
    with TestClient(create_public_app()) as public:
        assert public.get(response.headers['location']).status_code==404
        assert public.get('/data/finance/settlements/1/v1.json').status_code==404


def test_pdf_expenses_and_long_tables(db_session, sample, tmp_path, monkeypatch):
    from backend.services.settlement_document_service import SettlementDocumentService
    from backend.services.expense_service import ExpenseService
    from backend.models.owner_settlement import ExpenseCategory
    from pypdf import PdfReader
    monkeypatch.setattr('backend.services.expense_service.business_today',lambda:date(2026,10,31))
    category=ExpenseCategory(code='pdf-test',name='Sintética',active=True)
    db_session.add(category);db_session.commit()
    es=ExpenseService()
    expense=es.create(db_session,property_id=sample['property'].id,category_id=category.id,expense_date=date(2026,9,1),concept='Reparación sintética',base_amount='100',vat_rate='0',withholding_rate='0')
    es.pay(db_session,expense.id,effective_date=date(2026,9,10),amount='100',paid_by='manager',request_key=str(uuid4()))
    item=draft(db_session,sample);service.close(db_session,item.id,item.fingerprint)
    docs=SettlementDocumentService(tmp_path/'documents')
    docs.generate(db_session,item.id)
    text='\n'.join(p.extract_text() for p in PdfReader(docs.download(db_session,item.id,1)[1]).pages)
    assert 'Reparación sintética' in text and '150,00' in text
    assert '250,00' in text # Fee base does not become income less expenses.
    from backend.services.settlement_pdf import render_settlement_pdf
    from io import BytesIO
    row=dict(item.snapshot['rows'][0])
    payload=dict(id=item.id,identity=item.snapshot['document_identity'],legacy_identity=False,
        start=str(item.period_start),end=str(item.period_end),closed_at=str(item.closed_at),totals=item.snapshot['totals'],
        rows=[{**row,'concept':f'Línea sintética larga {i} '+('texto ' * 15)} for i in range(60)],
        payouts=[],paid='0.00',pending='150.00')
    reader=PdfReader(BytesIO(render_settlement_pdf(payload,'2026-09-30')))
    assert len(reader.pages)>2
    all_text='\n'.join(p.extract_text() for p in reader.pages)
    assert all(f'Línea sintética larga {i}' in all_text for i in range(60))
    assert all('Página' in p.extract_text() for p in reader.pages)


def test_pdf_adjustments_and_multipage(db_session, sample, tmp_path):
    from backend.services.settlement_document_service import SettlementDocumentService
    from pypdf import PdfReader
    documents=SettlementDocumentService(tmp_path/'documents')
    first=draft(db_session,sample);service.close(db_session,first.id,first.fingerprint)
    refund(db_session,sample)
    adjustment=draft(db_session,sample);service.close(db_session,adjustment.id,adjustment.fingerprint)
    documents.generate(db_session,adjustment.id)
    reader=PdfReader(documents.download(db_session,adjustment.id,1)[1])
    text='\n'.join(p.extract_text() for p in reader.pages)
    assert 'AJUSTES' in text and '-250,00' in text and '50,00' in text
    assert 'Regularización honorarios' in text and '-50,00' not in text
    assert 'RESULTADO LIQUIDACIÓN' in text and '-200,00' in text
    assert len(reader.pages)>=1


def test_admin_close_endpoint_and_validation_errors(client, db_session, sample):
    item = draft(db_session, sample)
    response = client.post(f'/settlements/{item.id}/close', data={'fingerprint':item.fingerprint}, follow_redirects=False)
    assert response.status_code == 303
    assert db_session.get(OwnerSettlement, item.id).status == 'closed'
    response = client.post('/expenses/new', data={'property_id':'invalid'})
    assert response.status_code == 200
    assert 'alert-danger' in response.text
    assert '"detail"' not in response.text
