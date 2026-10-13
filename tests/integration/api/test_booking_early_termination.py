from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4
import pytest
from sqlalchemy import select, func, text, event
from sqlalchemy.exc import IntegrityError
from backend.models import Booking, Property, Room, BookingCharge, Payment, PaymentAllocation, BookingFinancialTerms
from backend.models.booking_early_termination import BookingEarlyTermination
from backend.services.booking_early_termination_service import BookingEarlyTerminationService
from backend.services.financial_service import FinancialService
from backend.services.booking_service import BookingService
from backend.repositories.booking_repository import BookingRepository
from backend.core.public_availability import first_commercial_gap
from tests.integration.api.test_sepa_collections import scenario

TODAY = date(2026, 10, 13)
END = date(2027, 6, 30)
LAST = date(2026, 10, 31)


def test_optional_invoice_summary_without_billing_module():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from backend.services.booking_early_termination_service import related_invoice_summaries
    engine=create_engine('sqlite://')
    try:
        with Session(engine) as db:
            assert related_invoice_summaries(db,[1])==[]
            db.execute(text('CREATE TABLE management_fee_invoices (id INTEGER PRIMARY KEY, settlement_id INTEGER, status TEXT)'))
            db.execute(text("INSERT INTO management_fee_invoices VALUES (2,1,'issued'),(1,1,'draft'),(3,2,'issued')"))
            assert related_invoice_summaries(db,[1])==[{'id':1,'status':'draft'},{'id':2,'status':'issued'}]
            assert related_invoice_summaries(db,[])==[]
    finally:
        engine.dispose()


def test_optional_invoice_summary_does_not_hide_incompatible_schema():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from sqlalchemy.exc import OperationalError
    from backend.services.booking_early_termination_service import related_invoice_summaries
    engine=create_engine('sqlite://')
    try:
        with Session(engine) as db:
            db.execute(text('CREATE TABLE management_fee_invoices (id INTEGER PRIMARY KEY)'))
            with pytest.raises(OperationalError):related_invoice_summaries(db,[1])
    finally:
        engine.dispose()


@pytest.fixture
def booking(db_session, monkeypatch):
    monkeypatch.setattr('backend.services.booking_early_termination_service.business_today', lambda: TODAY)
    monkeypatch.setattr('backend.core.business_time.business_today', lambda: TODAY)
    p = Property(name='Finca sintética', address='Calle de pruebas', city='Elche', owner='')
    db_session.add(p); db_session.flush()
    room = Room(property_id=p.id, code='EARLY-TEST', active=True, operational_since=date(2020,1,1))
    db_session.add(room); db_session.flush()
    b = Booking(room_id=room.id, check_in=date(2026,9,1), check_out=END, origin='manual', source_guest_name='Persona sintética')
    db_session.add(b); db_session.commit()
    return b


def preview(db, booking, exit=TODAY, last=LAST, **kwargs):
    return BookingEarlyTerminationService().preview(db, booking.id, exit, last, **kwargs)


def finish(db, booking, exit=TODAY, last=LAST, **kwargs):
    v = preview(db, booking, exit, last, **kwargs)
    return BookingEarlyTerminationService().confirm(db, booking.id, exit, last, expected=v['fingerprint'], request_key=str(uuid4()), **kwargs)


def charge(db, b, *, lifecycle='draft', start=date(2026,11,1), end=date(2026,12,1)):
    c=BookingCharge(booking_id=b.id, type='rent', concept='Renta sintética', direction='debit', amount=Decimal('400'),
        due_date=start, service_period_start=start, service_period_end=end, lifecycle=lifecycle,
        posted_at=datetime(2026,10,1) if lifecycle=='posted' else None)
    db.add(c); db.commit(); return c


def test_active_today_original_history_and_availability(db_session, booking):
    record=finish(db_session,booking)
    db_session.expire_all()
    assert booking.check_out==TODAY and record.original_check_out==END
    assert booking.early_termination_label=='Finalizada anticipadamente'
    assert booking.economic_check_out==date(2026,11,1)
    assert booking.origin=='manual' and booking.source_guest_name=='Persona sintética'
    assert BookingRepository().list_current(db_session,booking.room_id,TODAY)==[]
    assert first_commercial_gap([(booking.check_in,booking.check_out)],TODAY,0)[0]=='available_now'
    later=Booking(room_id=booking.room_id,check_in=TODAY,check_out=date(2026,11,1))
    db_session.add(later); db_session.commit()
    assert later.id!=booking.id


@pytest.mark.parametrize('exit,label', [(date(2026,10,10),'Finalizada anticipadamente'),(date(2026,10,20),'Salida anticipada programada')])
def test_past_actual_or_future_departure(db_session,booking,exit,label):
    finish(db_session,booking,exit)
    assert booking.early_termination_label==label
    assert bool(BookingRepository().list_current(db_session,booking.room_id,TODAY))==(exit>TODAY)


@pytest.mark.parametrize('exit,last', [(date(2026,8,31),LAST),(date(2026,9,1),LAST),(END,LAST),(date(2027,7,1),LAST),(TODAY,END),(TODAY,date(2026,8,31))])
def test_invalid_intervals(db_session,booking,exit,last):
    with pytest.raises(ValueError): preview(db_session,booking,exit,last)
    assert booking.check_out==END


def test_explicit_partial_month_policy_and_plan(db_session,booking):
    v=preview(db_session,booking,TODAY,TODAY)
    assert any('prorrateo' in b for b in v['blockers'])
    terms=BookingFinancialTerms(booking_id=booking.id,version=1,effective_from=booking.check_in,monthly_rent=Decimal('400'),usual_due_day=1,
        status='confirmed',confirmed_at=datetime(2026,9,1))
    db_session.add(terms);db_session.commit()
    finish(db_session,booking,TODAY,TODAY,accept_proration=True)
    rows=FinancialService.preview_for_booking(booking,terms)
    assert rows[-1].service_period_end==date(2026,10,14)
    assert rows[-1].amount==Decimal('167.74')
    assert len(rows)==2
    assert not FinancialService().create_charge(db_session,booking.id,'rent','No permitido',date(2026,11,1),'400',service_period_start=date(2026,11,1),service_period_end=date(2026,12,1)).success


@pytest.mark.parametrize('lifecycle', ['draft','posted'])
@pytest.mark.parametrize('paid', ['0','100','400'])
def test_affected_charges_block_without_deleting(db_session,booking,lifecycle,paid):
    c=charge(db_session,booking,lifecycle=lifecycle)
    if paid!='0':
        p=Payment(booking_id=booking.id,effective_date=TODAY,amount=Decimal(paid),direction='receipt',method='cash',lifecycle='posted',posted_at=datetime(2026,10,13))
        db_session.add(p);db_session.flush();db_session.add(PaymentAllocation(payment_id=p.id,charge_id=c.id,amount=Decimal(paid)));db_session.commit()
    v=preview(db_session,booking)
    assert v['affected_charges']==[c.id] and v['blockers']
    with pytest.raises(ValueError):finish(db_session,booking)
    assert db_session.get(BookingCharge,c.id).amount==400 and booking.check_out==END


def test_historical_paid_charge_preserved_and_no_preview_writes(db_session,booking):
    c=charge(db_session,booking,lifecycle='posted',start=date(2026,9,1),end=date(2026,10,1))
    before=db_session.connection().connection.total_changes
    v=preview(db_session,booking)
    assert db_session.connection().connection.total_changes==before
    assert not v['blockers']
    finish(db_session,booking)
    assert c.lifecycle=='posted' and c.amount==400


def test_stale_charge_and_idempotency(db_session,booking):
    service=BookingEarlyTerminationService();v=preview(db_session,booking);key=str(uuid4())
    booking.notes='Modificación posterior';db_session.commit()
    with pytest.raises(ValueError,match='cambiado'):
        service.confirm(db_session,booking.id,TODAY,LAST,expected=v['fingerprint'],request_key=key)
    v=preview(db_session,booking)
    record=service.confirm(db_session,booking.id,TODAY,LAST,expected=v['fingerprint'],request_key=key)
    repeat=service.confirm(db_session,booking.id,TODAY,LAST,expected=v['fingerprint'],request_key=key)
    assert record.id==repeat.id and db_session.scalar(select(func.count()).select_from(BookingEarlyTermination))==1
    with pytest.raises(ValueError):service.confirm(db_session,booking.id,TODAY,LAST,expected=v['fingerprint'],request_key=str(uuid4()))


def test_history_immutable_and_booking_edit_protected(db_session,booking):
    record=finish(db_session,booking)
    result=BookingService().update_manual_booking(db_session,booking.id,booking.check_in,END,None,None)
    assert not result.success
    with pytest.raises(IntegrityError):
        db_session.execute(text('UPDATE bookings SET check_out=:d WHERE id=:id'),{'d':str(END),'id':booking.id});db_session.commit()
    db_session.rollback()
    with pytest.raises(IntegrityError):
        db_session.execute(text('DELETE FROM booking_early_terminations WHERE id=:id'),{'id':record.id});db_session.commit()
    db_session.rollback()
    assert not BookingService().delete_booking(db_session,booking).success


def test_rollback_after_date_update(db_session,booking):
    def fail(*_): raise RuntimeError('Injected history insertion failure')
    event.listen(BookingEarlyTermination,'before_insert',fail)
    try:
        with pytest.raises(RuntimeError): finish(db_session,booking)
    finally:event.remove(BookingEarlyTermination,'before_insert',fail)
    db_session.expire_all()
    assert booking.check_out==END and booking.early_termination is None


def test_form_review_no_write_and_explicit_confirmation(client,db_session,booking):
    url=f'/bookings/{booking.id}/early-termination'
    assert client.get(url).status_code==200
    fields=dict(effective_departure=str(TODAY),economic_last_day=str(LAST),request_key=str(uuid4()))
    r=client.post(url+'/preview',data=fields)
    assert r.status_code==200 and 'Confirmar finalización anticipada' in r.text and 'Último día a cargo' in r.text
    assert db_session.scalar(select(func.count()).select_from(BookingEarlyTermination))==0
    assert client.post(url+'/confirm',data=fields).status_code==409
    assert client.post(url+'/preview',data={'effective_departure':'invalid'}).status_code==422
    assert client.get(f'/bookings/{booking.id}').json()['early_termination_available']


def test_proration_acceptance_beside_warning_rechecks_without_writes(client,db_session,booking):
    url=f'/bookings/{booking.id}/early-termination/preview'
    fields=dict(effective_departure=str(TODAY),economic_last_day=str(TODAY),request_key=str(uuid4()),reason='Motivo conservado')
    response=client.post(url,data=fields)
    assert response.status_code==200
    warning='Revise y acepte expresamente el prorrateo existente por días naturales reales del último mes.'
    assert warning in response.text
    assert response.text.index(warning)<response.text.index('id="acceptProration"')
    assert response.text.count('id="acceptProration"')==1
    assert 'form="earlyTerminationForm"' in response.text
    assert 'Volver a revisar' in response.text
    assert 'id="earlyTerminationConfirmation"' not in response.text
    response=client.post(url,data={**fields,'accept_proration':'yes'})
    assert response.status_code==200 and warning not in response.text
    assert 'Prorrateo revisado.' in response.text and 'id="earlyTerminationConfirmation"' in response.text
    assert response.text.count('id="acceptProration"')==1 and 'Motivo conservado' in response.text
    response=client.post(url,data=fields)
    assert warning in response.text and 'id="earlyTerminationConfirmation"' not in response.text
    assert db_session.scalar(select(func.count()).select_from(BookingEarlyTermination))==0
    assert booking.check_out==END


def test_concurrent_same_request_is_one_event(db_session,booking):
    from concurrent.futures import ThreadPoolExecutor
    from sqlalchemy.orm import Session
    engine=db_session.get_bind();bid=booking.id;v=preview(db_session,booking);key=str(uuid4());db_session.rollback()
    def run():
        with Session(engine) as db:return BookingEarlyTerminationService().confirm(db,bid,TODAY,LAST,expected=v['fingerprint'],request_key=key).id
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:run(),range(2)))
    assert results[0]==results[1]


def test_conflicting_booking_is_reported_and_never_modified(db_session,booking):
    other=Booking(room_id=booking.room_id,check_in=date(2026,10,1),check_out=date(2026,10,20))
    db_session.add(other);db_session.commit()
    v=preview(db_session,booking)
    assert other.id in v['conflicts']
    with pytest.raises(ValueError):finish(db_session,booking)
    assert other.check_out==date(2026,10,20) and booking.check_out==END


@pytest.mark.parametrize('state',['prepared','exported','presented'])
def test_sepa_incompatible_preserves_instruction_and_artifact(db_session,scenario,monkeypatch,state):
    from tests.integration.api.test_sepa_collections import create
    from backend.models.sepa_collection import SepaExportArtifact,SepaDebit
    monkeypatch.setattr('backend.services.booking_early_termination_service.business_today',lambda:TODAY)
    service,b,_,_,charges=scenario
    batch=create(db_session,scenario)
    if state in {'exported','presented'}:service.export(db_session,batch.id)
    if state=='presented':service.present(db_session,batch.id)
    charges[0].service_period_start=date(2026,11,1);charges[0].service_period_end=date(2026,12,1);db_session.commit()
    artifact=db_session.scalar(select(SepaExportArtifact));saved_hash=artifact.sha256 if artifact else None
    v=preview(db_session,b)
    assert v['affected_debits'] and any('SEPA' in e for e in v['blockers'])
    with pytest.raises(ValueError):finish(db_session,b)
    assert db_session.get(type(batch),batch.id).status==state
    assert (db_session.scalar(select(SepaExportArtifact)).sha256 if artifact else None)==saved_hash
    assert db_session.scalar(select(func.count()).select_from(Payment))==0


def test_import_conflict_is_warning_without_date_or_identity_reversal(db_session,booking):
    from tests.unit.services.test_ical_sync_service import setup_calendar,service_for,imported
    room,cal=setup_calendar(db_session,'early')
    booking.room_id=room.id;booking.room_calendar_id=cal.id;booking.origin=cal.platform.slug;booking.external_reference='SYNTHETIC-UID';db_session.commit()
    uid=booking.ical_uid
    finish(db_session,booking)
    result=service_for([imported('SYNTHETIC-UID',booking.check_in,END,summary='Different source name')]).synchronize(db_session,cal.id)
    assert result.success and result.data.early_termination_conflicts==1 and result.data.has_warnings
    db_session.expire_all()
    assert booking.check_out==TODAY and booking.ical_uid==uid and booking.source_guest_name=='Persona sintética'
    assert booking.early_termination.source_state.source_check_out==END
    result=BookingService().upsert_imported_booking(db_session,cal.id,'SYNTHETIC-UID',booking.check_in,END)
    assert result.success and booking.check_out==TODAY
    result=service_for([imported('SYNTHETIC-UID',booking.check_in,TODAY)]).synchronize(db_session,cal.id)
    assert result.success and result.data.early_termination_conflicts==0


def test_master_export_releases_effective_day_and_has_no_private_history(db_session,booking):
    from backend.models.platform import Platform
    from backend.services.master_calendar_service import MasterCalendarService
    from icalendar import Calendar
    p=Platform(name='Test export',slug='test-export',active=True,supports_export=True)
    db_session.add(p);db_session.commit()
    uid=booking.ical_uid
    finish(db_session,booking,reason='PRIVATE_REASON_TEST')
    exported=MasterCalendarService().export_for_platform(db_session,booking.room.master_calendar_token,p.slug)
    event=[e for e in Calendar.from_ical(exported.content).walk() if e.name=='VEVENT'][0]
    assert event.decoded('DTEND')==TODAY and str(event['UID'])==uid+'@rentalmanager'
    assert b'PRIVATE_REASON_TEST' not in exported.content and b'economic' not in exported.content
