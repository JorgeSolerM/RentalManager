import sqlite3

from backend.models.property import Property
from backend.public.map_locations import Address, LocationCache
from backend.services.geolocation_incident_service import geolocation_incidents


def setup_cache(tmp_path, monkeypatch):
    cache = LocationCache(tmp_path / "geo.sqlite3")
    cache.initialize()
    monkeypatch.setenv("PUBLIC_GEOCODING_CACHE", str(cache.path))
    return cache


def prop(db, name="Finca sintética"):
    value = Property(name=name, address="Calle Ejemplo 10", owner="Titular sintético", street="Calle Ejemplo", street_number="10", city="Elche", active=True, is_published=True)
    db.add(value); db.commit()
    return value


def entry(cache, property_obj, status, reason="ambiguous"):
    with sqlite3.connect(cache.path) as db:
        db.execute("INSERT OR REPLACE INTO locations VALUES (?,?,?,?,?,?,?,?)", (
            Address.of(property_obj).key, status, None, None, reason, 1794500000, 1, 0))


def test_pending_review_provider_error_and_auto_resolution(db_session,tmp_path,monkeypatch):
    cache=setup_cache(tmp_path,monkeypatch); p=prop(db_session)
    initial=geolocation_incidents(db_session)
    assert len(initial)==1 and "Pendiente" in initial[0].title
    assert "Calle Ejemplo 10, Elche" in initial[0].detail
    for status,reason,label in [("review","ambiguous","Requiere revisión"),("error","http_429","Error del proveedor")]:
        entry(cache,p,status,reason)
        current=geolocation_incidents(db_session)
        assert len(current)==1 and current[0].key==initial[0].key
        assert label in current[0].title and "Último intento:" in current[0].detail
        assert current[0].target_url==f"/properties/{p.id}"
    entry(cache,p,"verified")
    assert geolocation_incidents(db_session)==[]
    p.street_number="11";db_session.commit()
    assert "Pendiente" in geolocation_incidents(db_session)[0].title


def test_reading_incidents_does_not_write_or_call_provider(db_session,tmp_path,monkeypatch):
    cache=setup_cache(tmp_path,monkeypatch);p=prop(db_session)
    entry(cache,p,"review")
    monkeypatch.setattr(LocationCache,"resolve",lambda *a,**kw: (_ for _ in ()).throw(AssertionError("Network path forbidden")))
    # WAL checkpointing can change main-file bytes without any data mutation.
    # Keep an observer open and check logical state plus commits by other readers.
    with sqlite3.connect(cache.path.as_uri()+"?mode=ro",uri=True) as observer:
        before=list(observer.iterdump())
        version=observer.execute("PRAGMA data_version").fetchone()
        for _ in range(3): assert len(geolocation_incidents(db_session))==1
        assert before==list(observer.iterdump())
        assert version==observer.execute("PRAGMA data_version").fetchone()
    p.is_published=False;db_session.commit()
    assert geolocation_incidents(db_session)==[]


def test_dashboard_renders_geolocation_alongside_existing_incidents(client,db_session,tmp_path,monkeypatch):
    cache=setup_cache(tmp_path,monkeypatch);p=prop(db_session)
    entry(cache,p,"review")
    response=client.get("/")
    assert response.status_code==200
    assert "Geolocalización · Requiere revisión" in response.text
    assert "Finca sintética" in response.text
    assert "Calle Ejemplo 10, Elche" in response.text
    entry(cache,p,"verified")
    assert "Geolocalización ·" not in client.get("/").text
