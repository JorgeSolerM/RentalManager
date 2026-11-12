import html
import json
import re
import sqlite3
from decimal import Decimal
from datetime import date
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

from backend.public.map_locations import Address, LocationCache, verified_result, catalog_map
from tests.integration.public.test_public_storefront import public_context, add_public_room, TODAY
from backend.public.service import PublicRoomService
from backend.models.booking import Booking
from backend.models.room import Room
from sqlalchemy import event


ADDRESS = Address('Calle Ejemplo', '10', 'Elche')


def result(**overrides):
    value = {'lat': '38.25', 'lon': '-0.70', 'address': {'road': 'Calle Ejemplo', 'house_number': '10', 'city': 'Elx'}}
    value.update(overrides)
    return value


def test_exact_verification_and_ambiguity():
    assert verified_result(ADDRESS, [result()])[0] == 'verified'
    assert verified_result(ADDRESS, [result(), result(lat='38.26')])[2] == 'ambiguous'
    for detail in ({'road':'Ejemplo','city':'Elche'}, {'road':'Otra','house_number':'10','city':'Elche'}, {'road':'Ejemplo','house_number':'10','city':'Madrid'}):
        assert verified_result(ADDRESS, [result(address=detail)])[0] == 'review'
    assert verified_result(ADDRESS, [result(lat='nan')])[0] == 'review'


def test_cache_concurrency_reuses_one_request(tmp_path):
    cache = LocationCache(tmp_path/'locations.sqlite3'); cache.initialize()
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(200,json=[result()])
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert list(pool.map(lambda _: cache.resolve(ADDRESS,client=client), range(2))) == ['verified','verified']
    assert len(calls) == 1
    assert cache.read_many({ADDRESS.key})[ADDRESS.key]['latitude'] == 38.25
    assert Address('Ejemplo','11','Elche').key != ADDRESS.key


def test_provider_error_stops_and_cooldown_does_not_sleep(tmp_path):
    cache = LocationCache(tmp_path/'locations.sqlite3'); cache.initialize()
    calls = []
    def respond(request):
        calls.append(request); return httpx.Response(429)
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        assert cache.resolve(ADDRESS,client=client) == 'error'
        assert cache.resolve(Address('Otra','1','Elche'),client=client,sleep=lambda _: pytest.fail('Long cooldown sleep')) == 'error'
        assert cache.resolve(ADDRESS,client=client) == 'error'
    assert len(calls) == 1


def test_global_throttle_and_permanent_review_cache(tmp_path):
    cache = LocationCache(tmp_path/'locations.sqlite3'); cache.initialize()
    now = [100.0]; sleeps = []
    def sleep(seconds): sleeps.append(seconds); now[0] += seconds
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200,json=[]))) as client:
        for address in (ADDRESS, Address('Otra','1','Elche'), ADDRESS):
            assert cache.resolve(address,client=client,clock=lambda:now[0],sleep=sleep) == 'review'
    assert sleeps == [16]


def test_catalog_map_exact_selection_privacy_and_address_change(public_context, db_session, tmp_path, monkeypatch):
    client, store = public_context
    prop, room = add_public_room(db_session, store)
    monkeypatch.setenv('PUBLIC_MAP_ENABLED','1')
    path = tmp_path/'locations.sqlite3'; monkeypatch.setenv('PUBLIC_GEOCODING_CACHE',str(path))
    cache = LocationCache(path); cache.initialize()
    address = Address.of(prop)
    response_data = result(address={'road':prop.street,'house_number':prop.street_number,'city':prop.city})
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200,json=[response_data]))) as geocoder:
        cache.resolve(address,client=geocoder)
    response = client.get('/')
    assert response.status_code == 200
    payload = json.loads(html.unescape(re.search(r'data-map-payload="([^"]+)"',response.text)[1]))
    assert len(payload['properties']) == 1
    assert Decimal(payload['properties'][0]['rooms'][0]['price']) == Decimal('650')
    assert payload['properties'][0]['rooms'][0]['slug'] == room.public_slug
    for private in ('Private owner','Private street','Internal city','entlo'):
        assert private not in json.dumps(payload)
    assert 'https://tile.openstreetmap.org' in response.headers['content-security-policy']
    assert 'https://tile.openstreetmap.org' not in client.get('/contacto').headers['content-security-policy']
    assert catalog_map(db_session, [])['properties'] == []
    prop.street_number = '999'; db_session.commit()
    rooms = PublicRoomService().list_rooms(db_session,today=TODAY)
    assert catalog_map(db_session,rooms)['omitted'] == 1
    assert len(rooms) == 1


def test_map_disabled_by_default(public_context):
    client,_ = public_context
    response = client.get('/')
    assert 'data-map-open' not in response.text
    assert 'tile.openstreetmap.org' not in response.headers['content-security-policy']


def test_map_uses_filtered_dates_and_publication(public_context, db_session, tmp_path, monkeypatch):
    client,store = public_context
    prop,room = add_public_room(db_session,store)
    monkeypatch.setenv('PUBLIC_MAP_ENABLED','1')
    monkeypatch.setenv('PUBLIC_GEOCODING_CACHE',str(tmp_path/'cache.sqlite3'))
    cache=LocationCache();cache.initialize()
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200,json=[result(address={'road':prop.street,'house_number':prop.street_number,'city':prop.city})]))) as geocoder:
        cache.resolve(Address.of(prop),client=geocoder)
    db_session.add(Booking(room_id=room.id,origin='manual',check_in=date(2026,9,1),check_out=date(2026,10,1)))
    db_session.commit()
    def data(url):
        response=client.get(url)
        return json.loads(html.unescape(re.search(r'data-map-payload="([^"]+)"',response.text)[1]))
    assert len(data('/')['properties']) == 1
    assert data('/?check_in=2026-09-05&check_out=2026-09-10')['properties'] == []
    assert len(data('/?check_in=2026-10-01&check_out=2026-11-01&sort=price_desc')['properties']) == 1
    room.is_published=False;db_session.commit()
    assert data('/')['properties'] == []


def test_grouping_one_marker_and_constant_query_count(public_context, db_session, tmp_path, monkeypatch):
    _,store=public_context
    prop,room=add_public_room(db_session,store)
    second=Room(property_id=prop.id,code='DEMO2',public_slug='demo-two',active=True)
    db_session.add(second);db_session.commit()
    monkeypatch.setenv('PUBLIC_MAP_ENABLED','1')
    monkeypatch.setenv('PUBLIC_GEOCODING_CACHE',str(tmp_path/'cache.sqlite3'))
    cache=LocationCache();cache.initialize()
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200,json=[result(address={'road':prop.street,'house_number':prop.street_number,'city':prop.city})]))) as geocoder:
        cache.resolve(Address.of(prop),client=geocoder)
    card=PublicRoomService().list_rooms(db_session,today=TODAY)[0]
    cards=[card,card.model_copy(update={'slug':'demo-two'})]
    queries=[]
    def count(*args): queries.append(args[2])
    event.listen(db_session.bind,'before_cursor_execute',count)
    try:
        payload=catalog_map(db_session,cards)
    finally:
        event.remove(db_session.bind,'before_cursor_execute',count)
    assert len(queries)==1
    assert len(payload['properties'])==1
    assert len(payload['properties'][0]['rooms'])==2
