from datetime import date, datetime, timedelta, timezone

from backend.models.booking import Booking
from backend.models.guest import Guest
from backend.models.platform import Platform
from backend.models.property import Property
from backend.models.room import Room
from backend.models.room_calendar import RoomCalendar


def test_dashboard_is_operational_and_reuses_booking_modal(client):
    response = client.get("/")
    assert response.status_code == 200
    for text in (
        "Ocupación", "ocupadas", "libres", "Entradas hoy", "Salidas hoy",
        "Próximas entradas", "Próximas salidas", "Incidencias",
        "Disponibilidad próxima", "Plataformas",
    ):
        assert text in response.text
    assert "/static/css/dashboard.css" in response.text
    assert "/static/js/bookings.js" in response.text
    assert 'id="bookingModal"' in response.text
    assert 'href="/gantt/"' in response.text
    assert "Ver calendario" not in response.text
    assert "Última actualización fiable: —" in response.text
    assert "Éste será el centro de control" not in response.text
    assert 'role="img"' in response.text
    assert "0 habitaciones ocupadas de 0; 0 libres; ocupación 0,0 %." in response.text


def test_dashboard_excludes_archived_room_and_its_future_booking(
    client, db_session
):
    property_obj = Property(
        name="Archived dashboard", address="A", city="Madrid", owner="O",
        active=True,
    )
    db_session.add(property_obj)
    db_session.flush()
    room = Room(
        property_id=property_obj.id, code="ARCHIVED-DASH", display_order=1,
        base_price=500, active=False,
    )
    db_session.add(room)
    db_session.flush()
    db_session.add(Booking(
        room_id=room.id, origin="manual",
        check_in=date.today() + timedelta(days=1),
        check_out=date.today() + timedelta(days=10),
    ))
    db_session.commit()

    response = client.get("/")

    assert response.status_code == 200
    assert "ARCHIVED-DASH" not in response.text
    assert "0 habitaciones ocupadas de 0; 0 libres; ocupación 0,0 %." in response.text


def test_preparation_room_is_excluded_until_put_into_operation(
    client, db_session
):
    property_obj = Property(
        name="Preparation dashboard", address="A", city="Madrid", owner="O",
        active=True,
    )
    room = Room(
        property=property_obj, code="PREPARATION", display_order=1,
        base_price=None, active=True, is_published=False,
        operational_since=None,
    )
    db_session.add_all([property_obj, room])
    db_session.commit()

    preparation = client.get("/")
    room.operational_since = date.today()
    db_session.commit()
    operational = client.get("/")

    assert "0 habitaciones ocupadas de 0; 0 libres; ocupación 0,0 %." in preparation.text
    assert "0 habitaciones ocupadas de 1; 1 libres; ocupación 0,0 %." in operational.text


def test_dashboard_formats_single_reliable_platform_update(client, db_session):
    synced_at = datetime.now(timezone.utc).replace(tzinfo=None)
    property_obj = Property(
        name="Reliable", address="A", city="Madrid", owner="O", active=True
    )
    platform = Platform(
        name="Reliable Platform", slug="reliable-platform", active=True,
        supports_import=True, supports_export=True,
    )
    db_session.add_all([property_obj, platform]); db_session.flush()
    room = Room(
        property_id=property_obj.id, code="RELIABLE", display_order=1,
        base_price=500, active=True,
    )
    db_session.add(room); db_session.flush()
    db_session.add(RoomCalendar(
        room_id=room.id, platform_id=platform.id,
        import_url="https://example.com/feed.ics", active=True,
        automatic_sync_enabled=True, last_sync_status="ok",
        last_sync_at=synced_at,
        last_sync_attempt_at=synced_at,
    ))
    db_session.commit()

    response = client.get("/")
    assert response.status_code == 200
    assert "Última actualización fiable:" in response.text
    assert synced_at.strftime("%d/%m/%Y %H:%M") in response.text


def test_dashboard_assets_define_responsive_compact_layout():
    styles = open("backend/static/css/dashboard.css", encoding="utf-8").read()
    template = open("backend/templates/pages/dashboard.html", encoding="utf-8").read()
    assert "grid-template-columns:minmax(15rem,1.35fr) repeat(2" in styles
    assert "conic-gradient" in styles
    assert "dashboard-donut" in template
    assert "aria-label=" in template
    assert "@media (max-width:850px)" in styles
    assert "@media (max-width:576px)" in styles
    assert "dashboard-platform-icon" in styles
    assert 'class="booking-link' in template
    assert 'href="/rooms/{{ item.room_id }}"' in template
    for private in ("import_url", "master_calendar_token", "external_reference"):
        assert private not in template


def test_dashboard_does_not_render_private_booking_or_calendar_data(
    client, db_session
):
    property_obj = Property(
        name="Visible Property", address="A", city="Madrid", owner="O", active=True
    )
    platform = Platform(
        name="Visible Platform", slug="visible-platform", active=True,
        supports_import=True, supports_export=True,
    )
    db_session.add_all([property_obj, platform]); db_session.flush()
    room = Room(
        property_id=property_obj.id, code="VISIBLE", display_order=1,
        base_price=500, active=True, master_calendar_token="PRIVATE-ROOM-TOKEN",
    )
    guest = Guest(
        full_name="Visible Guest", phone="PRIVATE-PHONE",
        email="private@example.com", active=True,
    )
    db_session.add_all([room, guest]); db_session.flush()
    calendar = RoomCalendar(
        room_id=room.id, platform_id=platform.id,
        import_url="https://example.com/PRIVATE-ICAL-TOKEN.ics",
        active=True, automatic_sync_enabled=False,
    )
    db_session.add(calendar); db_session.flush()
    db_session.add(Booking(
        room_id=room.id, room_calendar_id=calendar.id, guest_id=guest.id,
        origin=platform.slug, external_reference="PRIVATE-EXTERNAL-REFERENCE",
        check_in=date.today(), check_out=date.today() + timedelta(days=2),
        notes="PRIVATE-NOTES",
    ))
    db_session.commit()

    response = client.get("/")
    assert response.status_code == 200
    assert "Visible Guest" in response.text
    for private in (
        "PRIVATE-ROOM-TOKEN", "PRIVATE-PHONE", "private@example.com",
        "PRIVATE-ICAL-TOKEN", "PRIVATE-EXTERNAL-REFERENCE", "PRIVATE-NOTES",
    ):
        assert private not in response.text
