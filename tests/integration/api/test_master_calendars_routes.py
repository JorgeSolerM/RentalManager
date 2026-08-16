from datetime import date

from fastapi.testclient import TestClient
from icalendar import Calendar
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app_factory import create_app
from backend.database.base import Base
from backend.database.session import get_db
from backend.models.booking import Booking
from backend.models.platform import Platform
from backend.models.property import Property
from backend.models.room import Room


def seed(db_session):
    property_obj = Property(name="Property", address="Address", city="Madrid", owner="Owner", active=True)
    db_session.add(property_obj)
    db_session.flush()
    room = Room(property_id=property_obj.id, code="R01", display_order=1, base_price=500, active=True)
    platform = Platform(name="HousingAnywhere", slug="housinganywhere", active=True, supports_import=True, supports_export=True)
    db_session.add_all([room, platform])
    db_session.flush()
    booking = Booking(room_id=room.id, origin="manual", check_in=date(2026, 5, 8), check_out=date(2026, 8, 31))
    db_session.add(booking)
    db_session.commit()
    return room, platform, booking


def test_public_calendar_headers_etag_and_generic_not_found(client, db_session):
    room, platform, _ = seed(db_session)
    url = f"/ical/rooms/{room.master_calendar_token}/{platform.slug}.ics"
    response = client.get(url)
    cached = client.get(url, headers={"If-None-Match": response.headers["etag"]})
    missing = client.get(f"/ical/rooms/invalid/{platform.slug}.ics")
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/calendar; charset=utf-8"
    assert response.headers["content-disposition"] == 'inline; filename="calendar.ics"'
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "must-revalidate" in response.headers["cache-control"]
    assert response.headers["etag"].startswith('W/"')
    assert str(Calendar.from_ical(response.content)["VERSION"]) == "2.0"
    assert cached.status_code == 304
    assert cached.content == b""
    assert missing.status_code == 404
    assert missing.json() == {"detail": "Calendario no encontrado."}


def test_regeneration_contract_revokes_old_url(client, db_session):
    room, platform, booking = seed(db_session)
    old_token = room.master_calendar_token
    old_uid = booking.ical_uid
    response = client.post(f"/master-calendars/rooms/{room.id}/regenerate", follow_redirects=False)
    db_session.refresh(room)
    db_session.refresh(booking)
    assert response.status_code == 303
    assert response.headers["location"] == f"/rooms/{room.id}?success=master_calendar_token_regenerated"
    assert room.master_calendar_token != old_token
    assert booking.ical_uid == old_uid
    assert client.get(f"/ical/rooms/{old_token}/{platform.slug}.ics").status_code == 404


def test_workspace_uses_configured_origin_and_never_request_host(client, db_session, monkeypatch):
    room, _, _ = seed(db_session)
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://calendar.example")
    response = client.get(f"/rooms/{room.id}", headers={"Host": "attacker.example"})
    assert response.status_code == 200
    assert "Copiar para HousingAnywhere" in response.text
    assert "https://calendar.example/ical/rooms/" in response.text
    assert 'data-master-calendar-url="http://attacker.example' not in response.text
    assert response.text.count("data-master-calendar-url") == 1
    assert 'name="export_url"' not in response.text
    assert 'name="referrer" content="no-referrer"' in response.text


def test_independent_http_sessions_see_regenerated_token(tmp_path):
    path = tmp_path / "independent_master_calendar.db"
    engine = create_engine(f"sqlite:///{path.as_posix()}", connect_args={"check_same_thread": False})
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(engine)
    setup = factory()
    room, platform, _ = seed(setup)
    room_id, slug, old_token = room.id, platform.slug, room.master_calendar_token
    setup.close()
    app = create_app(initialize_database=False)

    def independent_db():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = independent_db
    with TestClient(app) as client:
        assert client.get(f"/ical/rooms/{old_token}/{slug}.ics").status_code == 200
        assert client.post(f"/master-calendars/rooms/{room_id}/regenerate", follow_redirects=False).status_code == 303
        assert client.get(f"/ical/rooms/{old_token}/{slug}.ics").status_code == 404
    check = factory()
    new_token = check.get(Room, room_id).master_calendar_token
    check.close()
    with TestClient(app) as client:
        assert client.get(f"/ical/rooms/{new_token}/{slug}.ics").status_code == 200
    app.dependency_overrides.clear()
    engine.dispose()
