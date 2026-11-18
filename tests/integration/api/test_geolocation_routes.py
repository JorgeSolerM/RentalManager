import html
import re

from fastapi.testclient import TestClient
import pytest

from backend.api.routers import geolocation
from backend.app_factory import create_app
from backend.database.session import get_db
from backend.models.property import Property
from backend.public.map_locations import Address, LocationCache
from backend.services.geolocation_incident_service import geolocation_incidents


@pytest.fixture
def admin(db_session,tmp_path,monkeypatch):
    monkeypatch.setenv('PUBLIC_GEOCODING_CACHE',str(tmp_path/'cache.sqlite3'))
    monkeypatch.setenv('PUBLIC_GEOCODING_ADMIN_RETRY_ENABLED','1')
    p=Property(name='Finca de prueba',street='Ejemplo',street_number='10',city='Elche',address='',owner='',active=True,is_published=True)
    db_session.add(p);db_session.commit()
    LocationCache().initialize()
    app=create_app();app.dependency_overrides[get_db]=lambda:db_session
    with TestClient(app,base_url='http://127.0.0.1',client=('127.0.0.1',1234)) as c:yield c,p


def csrf(c,p):
    r=c.get(f'/properties/{p.id}/geolocation');assert r.status_code==200
    return html.unescape(re.search('name="csrf" value="([^"]+)"',r.text)[1])


def test_review_read_only_edit_reuses_modal_maps_encoded(admin,db_session):
    c,p=admin
    r=c.get(f'/properties/{p.id}/geolocation')
    assert r.status_code==200 and 'Pendiente' in r.text and 'Editar dirección' in r.text
    assert 'id="property-form"' in r.text and 'js/properties.js' in r.text
    assert 'query=Ejemplo+10%2C+Elche' in r.text
    assert 'No conservada en la caché anterior' in r.text
    assert LocationCache().read_many([Address.of(p).key])=={}


def test_retry_csrf_origin_and_stale_address(admin,db_session,monkeypatch):
    c,p=admin;url=f'/properties/{p.id}/geolocation/retry';called=[]
    monkeypatch.setattr(geolocation,'retry_address',lambda a:called.append(a) or 'verified')
    assert c.post(url).status_code==403
    token=csrf(c,p)
    assert c.post(url,data={'csrf':token},headers={'Origin':'https://evil.example'}).status_code==403
    p.street_number='11';db_session.commit()
    assert c.post(url,data={'csrf':token}).status_code==403 and not called
    token=csrf(c,p)
    r=c.post(url,data={'csrf':token},headers={'Origin':'null','Sec-Fetch-Site':'same-origin'})
    assert r.status_code==200 and 'Ubicación verificada' in r.text and len(called)==1


def test_address_save_existing_service_and_auto_incident_resolution(admin,db_session,monkeypatch):
    c,p=admin;token=csrf(c,p)
    import sqlite3
    original_key = Address.of(p).key
    with sqlite3.connect(LocationCache().path) as cache_db:
        cache_db.execute('INSERT INTO locations VALUES (?,?,?,?,?,?,?,?)',
            (original_key,'verified',38.2,-.7,'exact_street_number_city',1,1,0))
    assert geolocation_incidents(db_session)==[]
    r=c.post(f'/properties/{p.id}/geolocation/address',data={'csrf':token,'name':p.name,'street':'Calle Nueva','street_number':'12','city':'Elche'})
    assert r.status_code==200 and 'Dirección guardada' in r.text
    db_session.refresh(p);assert p.street=='Calle Nueva' and p.street_number=='12'
    entries = LocationCache().read_many([original_key, Address.of(p).key])
    assert entries[original_key]['status']=='verified'  # Preserve historical diagnostics.
    assert Address.of(p).key not in entries  # Never reuse the old point for the new address.
    assert len(geolocation_incidents(db_session))==1
    def resolve(a):
        import httpx
        with httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,json=[{'lat':'38.2','lon':'-.7','address':{'road':a.street,'house_number':a.number,'city':a.city}}]))) as client:
            return LocationCache().resolve_progressive(a,client=client)
    monkeypatch.setattr(geolocation,'retry_address',resolve)
    c.post(f'/properties/{p.id}/geolocation/retry',data={'csrf':csrf(c,p)})
    assert geolocation_incidents(db_session)==[]


def test_remote_client_and_host_rejected(admin):
    c,p=admin
    assert c.get(f'/properties/{p.id}/geolocation',headers={'Host':'evil.example'}).status_code==403
    with TestClient(c.app,base_url='http://127.0.0.1',client=('192.0.2.1',123)) as remote:
        assert remote.get(f'/properties/{p.id}/geolocation').status_code==403


def test_disabled_retry_does_not_call_provider(admin,monkeypatch):
    c,p=admin;monkeypatch.delenv('PUBLIC_GEOCODING_ADMIN_RETRY_ENABLED',raising=False)
    monkeypatch.setattr(LocationCache,'resolve_progressive',lambda *a,**kw:pytest.fail('No query'))
    r=c.post(f'/properties/{p.id}/geolocation/retry',data={'csrf':csrf(c,p)})
    assert r.status_code==200 and 'no están habilitados' in r.text


def test_public_app_excludes_management_routes(admin):
    from backend.public.app_factory import create_public_app
    with TestClient(create_public_app()) as public:
        assert public.get('/properties/1/geolocation').status_code==404
        assert public.post('/properties/1/geolocation/retry').status_code==404


def test_location_action_available_without_open_incidents(admin,db_session):
    import sqlite3
    c,p=admin
    with sqlite3.connect(LocationCache().path) as cache_db:
        cache_db.execute('INSERT INTO locations VALUES (?,?,?,?,?,?,?,?)',
            (Address.of(p).key,'verified',38.2,-.7,'exact_street_number_city',1,1,0))
    assert geolocation_incidents(db_session)==[]
    page=c.get('/properties/')
    assert page.status_code==200
    assert 'id="property-location-button"' in page.text and 'Actualizar ubicación' in page.text


@pytest.mark.parametrize('field,value',[('street','Otra calle'),('street_number','99'),('city','Otra ciudad')])
def test_physical_address_change_invalidates_incident_lookup(admin,db_session,field,value):
    import sqlite3
    c,p=admin;old_key=Address.of(p).key
    with sqlite3.connect(LocationCache().path) as cache_db:
        cache_db.execute('INSERT INTO locations VALUES (?,?,?,?,?,?,?,?)',
            (old_key,'verified',38.2,-.7,'exact_street_number_city',1,1,0))
    setattr(p,field,value);db_session.commit()
    assert Address.of(p).key != old_key
    assert len(geolocation_incidents(db_session))==1
    assert 'Pendiente' in geolocation_incidents(db_session)[0].title


def test_name_floor_door_changes_reuse_verified_location(admin,db_session,monkeypatch):
    import sqlite3
    c,p=admin;old_key=Address.of(p).key
    with sqlite3.connect(LocationCache().path) as cache_db:
        cache_db.execute('INSERT INTO locations VALUES (?,?,?,?,?,?,?,?)',
            (old_key,'verified',38.2,-.7,'exact_street_number_city',1,1,0))
    p.name='Nombre nuevo';p.floor='2';p.door='A';db_session.commit()
    assert Address.of(p).key == old_key and geolocation_incidents(db_session)==[]
    monkeypatch.setenv('PUBLIC_GEOCODER_USER_AGENT','Synthetic tests')
    monkeypatch.setattr(geolocation.httpx.Client,'get',lambda *a,**kw:pytest.fail('Verified address must not query provider'))
    assert geolocation.retry_address(Address.of(p))=='verified'
