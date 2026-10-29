from datetime import date, timedelta
from hashlib import sha256
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from backend.core.public_availability import add_calendar_months, terminal_available_from
from backend.models import Booking, Room
from backend.public.app_factory import create_public_app
from backend.public.database import get_public_db
from backend.public.collaborator_calendar import PREFIX, calendar_data
from backend.core.media_storage import MediaFileStore, MediaStoragePaths
from tests.integration.public.test_public_storefront import add_public_room

TODAY = date(2026, 11, 1)
TOKEN = 'synthetic-test-only-' + 'x' * 23
AUTH = {'Authorization': 'Bearer ' + TOKEN}


@pytest.fixture
def context(db_session, tmp_path, monkeypatch):
    monkeypatch.delenv('COLLABORATOR_CALENDAR_TOKEN_HASH_FILE',raising=False)
    monkeypatch.setenv('COLLABORATOR_CALENDAR_TOKEN_SHA256', sha256(TOKEN.encode()).hexdigest())
    monkeypatch.setattr('backend.public.collaborator_calendar.business_today', lambda: TODAY)
    store = MediaFileStore(MediaStoragePaths.from_root(tmp_path/'media'))
    prop, room = add_public_room(db_session, store)
    app = create_public_app(media_store=store)
    def db():
        yield db_session
    app.dependency_overrides[get_public_db] = db
    with TestClient(app) as client:
        yield client, prop, room


def booking(db, room, start, end, **kwargs):
    item = Booking(room_id=room.id, check_in=date.fromisoformat(start), check_out=date.fromisoformat(end), **kwargs)
    db.add(item); db.commit(); return item


@pytest.mark.parametrize('intervals,expected', [
    ([], '2026-11-01'),
    ([('2026-10-01','2026-12-01')], '2026-12-01'),
    ([('2026-10-01','2026-11-15'),('2027-02-01','2027-09-01')], None),
    ([('2026-12-01','2027-09-01')], None),
    ([('2026-10-01','2027-02-01'),('2027-03-01','2027-04-01')], '2027-04-01'),
    ([('2026-10-01','2027-07-01')], None),
    ([('2026-10-01','2027-01-01'),('2027-09-01','2027-10-01')], None),
    # Free now does not give today's availability when another stay is known.
    ([('2026-12-01','2027-01-01')], '2027-01-01'),
    ([('2026-10-01','2026-11-01')], '2026-11-01'),
    ([('2026-10-01','2027-05-01')], None),
    ([('2026-10-01','2027-04-30')], '2027-04-30'),
])
def test_terminal_availability_not_temporary_gaps(context, db_session, intervals, expected):
    client, _, room = context
    for start,end in intervals:
        booking(db_session,room,start,end)
    data = client.get(PREFIX+'/data', headers=AUTH).json()
    if expected is None:
        assert data['properties']==[]
    else:
        rows=data['properties'][0]['rooms']
        assert len(rows)==1 and rows[0]['available_from']==expected


def test_invalid_intervals_fail_closed_and_calendar_months():
    assert terminal_available_from([(TODAY,TODAY)],TODAY) is None
    assert terminal_available_from([(TODAY,TODAY-timedelta(days=1))],TODAY) is None
    assert add_calendar_months(date(2026,8,31),6)==date(2027,2,28)


@pytest.mark.parametrize('attribute,value', [('active',False),('is_published',False),('operational_since',None),('base_price',None),('public_slug',None)])
def test_non_commercial_rooms_excluded(context, db_session, attribute, value):
    client,_,room=context; setattr(room,attribute,value); db_session.commit()
    assert client.get(PREFIX+'/data',headers=AUTH).json()['properties']==[]


@pytest.mark.parametrize('attribute,value', [('active',False),('is_published',False),('public_title',None),('public_slug',None)])
def test_non_public_property_excluded(context, db_session, attribute, value):
    client,prop,_=context; setattr(prop,attribute,value); db_session.commit()
    assert client.get(PREFIX+'/data',headers=AUTH).json()['properties']==[]


def test_privacy_read_only_links_security_and_no_discovery(context,db_session):
    client,_,room=context
    b=booking(db_session,room,'2026-10-01','2026-12-01',source_guest_name='PRIVATE-OCCUPANT',
              notes='PRIVATE-NOTES',external_reference='PRIVATE-ICAL',price=9876)
    response=client.get(PREFIX+'/data',headers=AUTH)
    assert response.status_code==200
    row=response.json()['properties'][0]['rooms'][0]
    assert set(row)=={'name','listing_url','available_from','occupied'}
    assert set(row['occupied'][0])=={'start','end'}
    assert row['listing_url']==f'/habitaciones/{room.public_slug}'
    assert client.get(row['listing_url']).status_code==200
    for marker in ['PRIVATE-OCCUPANT','PRIVATE-NOTES','PRIVATE-ICAL','9876','Internal property','Private owner',TOKEN]:
        assert marker not in response.text
    for path in [PREFIX,PREFIX+'/data']:
        r=client.get(path,headers=AUTH)
        assert r.headers['referrer-policy']=='no-referrer'
        assert 'no-store' in r.headers['cache-control'] and 'noindex' in r.headers['x-robots-tag']
        assert 'set-cookie' not in r.headers
        assert client.post(path,headers=AUTH).status_code==405
    shell=client.get(PREFIX).text
    assert room.public_title not in shell and TOKEN not in shell
    assert '<form' not in shell
    for path in ['/','/sitemap.xml']:
        assert PREFIX not in client.get(path).text
    for path in ['/docs','/openapi.json','/persons','/bookings','/gantt/']:
        assert client.get(path).status_code==404
    db_session.refresh(b)
    assert b.check_out==date(2026,12,1) and db_session.query(Booking).count()==1


def test_missing_wrong_revoked_and_disabled_token(context,monkeypatch):
    client,_,_=context
    assert client.get(PREFIX+'/data').status_code==401
    assert client.get(PREFIX+'/data',headers={'Authorization':TOKEN}).status_code==401
    assert client.get(PREFIX+'/data?token='+TOKEN).status_code==401
    assert client.get(PREFIX+'/data',headers={'Authorization':'Bearer '+('z'*43)}).status_code==401
    assert client.get(PREFIX+'/data',headers=AUTH).status_code==200
    monkeypatch.setenv('COLLABORATOR_CALENDAR_TOKEN_SHA256',sha256(b'revoked').hexdigest())
    r=client.get(PREFIX+'/data',headers=AUTH)
    assert r.status_code==401 and TOKEN not in r.text and 'no-store' in r.headers['cache-control']
    monkeypatch.delenv('COLLABORATOR_CALENDAR_TOKEN_SHA256')
    assert client.get(PREFIX).status_code==404
    assert client.get(PREFIX+'/data',headers=AUTH).status_code==404


def test_private_digest_file_rotation_without_restart(context,monkeypatch,tmp_path):
    client,_,_=context
    path=tmp_path/'token.sha256'; path.write_text(sha256(TOKEN.encode()).hexdigest())
    monkeypatch.setenv('COLLABORATOR_CALENDAR_TOKEN_HASH_FILE',str(path))
    assert client.get(PREFIX+'/data',headers=AUTH).status_code==200
    path.write_text(sha256(b'new-secret').hexdigest())
    assert client.get(PREFIX+'/data',headers=AUTH).status_code==401
    path.unlink()
    assert client.get(PREFIX+'/data',headers=AUTH).status_code==404


@pytest.mark.parametrize('departure',[date(2026,11,1),date(2026,12,1)])
def test_confirmed_early_departure_not_economic_end(context,db_session,monkeypatch,departure):
    from backend.services.booking_early_termination_service import BookingEarlyTerminationService
    client,_,room=context
    monkeypatch.setattr('backend.services.booking_early_termination_service.business_today',lambda:TODAY)
    b=booking(db_session,room,'2026-10-01','2027-09-01')
    service=BookingEarlyTerminationService()
    args=dict(reason='Prueba sintética',accept_proration=True)
    view=service.preview(db_session,b.id,departure,date(2027,1,31),**args)
    service.confirm(db_session,b.id,departure,date(2027,1,31),expected=view['fingerprint'],request_key=str(uuid4()),**args)
    row=client.get(PREFIX+'/data',headers=AUTH).json()['properties'][0]['rooms'][0]
    assert row['available_from']==departure.isoformat()


def test_ical_expected_departure_and_late_future_change(context,db_session):
    client,_,room=context
    b=booking(db_session,room,'2026-10-01','2026-12-01',origin='ical',expected_departure_date=TODAY)
    assert client.get(PREFIX+'/data',headers=AUTH).json()['properties'][0]['rooms'][0]['available_from']=='2026-12-01'
    b.check_out=date(2027,9,1); db_session.commit()
    assert client.get(PREFIX+'/data',headers=AUTH).json()['properties']==[]
    # Removing a booking through existing domain workflows is reflected on read;
    # the public endpoint itself has no cancellation operation.
    db_session.delete(b); db_session.commit()
    assert client.get(PREFIX+'/data',headers=AUTH).json()['properties'][0]['rooms'][0]['available_from']==TODAY.isoformat()


def test_overlap_geometry_and_fixed_query_count(context,db_session):
    _,prop,room=context
    for index in range(8):
        extra=Room(property_id=prop.id,code=f'TEST-{index}',active=True,operational_since=TODAY,
                   public_title=f'Room {index}',public_description='Synthetic',public_slug=f'test-{index}',
                   is_published=True,base_price=400,minimum_stay_months=0)
        extra.features=list(room.features); db_session.add(extra)
    booking(db_session,room,'2026-10-01','2026-12-15')
    booking(db_session,room,'2026-12-01','2027-01-01')
    calls=[]
    def capture(conn,cursor,statement,parameters,context,executemany):
        if statement.lstrip().upper().startswith('SELECT'):calls.append(statement)
    engine=db_session.get_bind(); event.listen(engine,'before_cursor_execute',capture)
    try:
        result=calendar_data(db_session,today=TODAY,listing_path=lambda slug:'/habitaciones/'+slug)
    finally:event.remove(engine,'before_cursor_execute',capture)
    assert len(calls)<16
    original=next(r for r in result['properties'][0]['rooms'] if r['name']==room.public_title)
    assert original['occupied']==[{'start':'2026-11-01','end':'2027-01-01'}]
