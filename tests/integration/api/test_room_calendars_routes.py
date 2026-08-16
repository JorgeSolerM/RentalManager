from datetime import date, datetime, timedelta

from sqlalchemy import select

from backend.models.booking import Booking
from backend.models.platform import Platform
from backend.models.property import Property
from backend.models.room import Room
from backend.models.room_calendar import RoomCalendar


def setup_room_and_platform(db_session, platform_active=True):
    property_obj = Property(
        name="Piso Calendarios", address="Calle Uno", city="Elche",
        owner="HSI", active=True,
    )
    db_session.add(property_obj)
    db_session.flush()
    room = Room(
        property_id=property_obj.id, code="H01", display_order=1,
        base_price=350, active=True,
    )
    platform = Platform(
        name="Booking.com", slug="booking", active=platform_active,
        supports_import=True, supports_export=True,
    )
    db_session.add_all([room, platform])
    db_session.commit()
    return room, platform


def test_room_calendar_http_create_update_toggle_delete_contracts(client, db_session):
    room, platform = setup_room_and_platform(db_session)
    create_response = client.post(
        "/room-calendars/create",
        data={
            "room_id": room.id,
            "platform_id": platform.id,
            "import_url": "https://example.com/in.ics",
            "export_url": "https://example.com/out.ics",
        },
        follow_redirects=False,
    )
    calendar = db_session.scalar(select(RoomCalendar))
    calendar.last_sync_at = datetime(2026, 8, 1, 12, 0)
    db_session.commit()
    update_response = client.post(
        f"/room-calendars/update/{calendar.id}",
        data={"import_url": "https://example.com/new.ics", "export_url": ""},
        follow_redirects=False,
    )
    toggle_response = client.post(
        f"/room-calendars/toggle/{calendar.id}", follow_redirects=False
    )
    delete_response = client.post(
        f"/room-calendars/delete/{calendar.id}", follow_redirects=False
    )

    assert create_response.status_code == 303
    assert create_response.headers["location"] == (
        f"/rooms/{room.id}?success=room_calendar_created"
    )
    assert update_response.headers["location"] == (
        f"/rooms/{room.id}?success=room_calendar_updated"
    )
    assert toggle_response.headers["location"] == (
        f"/rooms/{room.id}?success=room_calendar_toggled"
    )
    assert delete_response.headers["location"] == (
        f"/rooms/{room.id}?success=room_calendar_deleted"
    )
    assert calendar.last_sync_at == datetime(2026, 8, 1, 12, 0)
    assert db_session.get(RoomCalendar, calendar.id) is None


def test_room_calendar_http_errors_and_blocked_history(client, db_session):
    room, platform = setup_room_and_platform(db_session)
    calendar = RoomCalendar(
        room_id=room.id, platform_id=platform.id,
        import_url="https://example.com/in.ics", active=True,
    )
    db_session.add(calendar)
    db_session.flush()
    db_session.add(Booking(
        room_id=room.id, room_calendar_id=calendar.id, origin="booking",
        external_reference="UID-1", check_in=date(2026, 9, 1),
        check_out=date(2026, 9, 5),
    ))
    db_session.commit()

    blocked = client.post(
        f"/room-calendars/delete/{calendar.id}", follow_redirects=False
    )
    missing = client.post("/room-calendars/toggle/999", follow_redirects=False)

    assert blocked.status_code == 303
    assert blocked.headers["location"] == (
        f"/rooms/{room.id}?error=room_calendar_has_bookings"
    )
    assert missing.status_code == 404
    assert db_session.get(RoomCalendar, calendar.id) is not None


def test_workspace_shows_configuration_history_and_unknown_guest(client, db_session):
    room, active_platform = setup_room_and_platform(db_session)
    inactive_platform = Platform(
        name="Legacy Platform", slug="legacy", active=False,
        supports_import=True, supports_export=False,
    )
    db_session.add(inactive_platform)
    db_session.flush()
    active_calendar = RoomCalendar(
        room_id=room.id, platform_id=active_platform.id,
        import_url="https://example.com/active.ics", active=True,
    )
    legacy_calendar = RoomCalendar(
        room_id=room.id, platform_id=inactive_platform.id,
        import_url="https://example.com/legacy.ics", active=False,
    )
    db_session.add_all([active_calendar, legacy_calendar])
    db_session.flush()
    today = date.today()
    db_session.add(Booking(
        room_id=room.id, room_calendar_id=active_calendar.id,
        guest_id=None, origin="booking", external_reference="UNKNOWN-GUEST",
        check_in=today - timedelta(days=1),
        check_out=today + timedelta(days=1),
    ))
    db_session.commit()

    response = client.get(f"/rooms/{room.id}")

    assert response.status_code == 200
    assert "Huésped desconocido" in response.text
    assert "Booking.com" in response.text
    assert "https://example.com/active.ics" in response.text
    assert "Legacy Platform" in response.text
    assert "Platform inactiva" in response.text
    assert "Sin configurar" not in response.text
