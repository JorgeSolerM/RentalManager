from datetime import date, datetime, timezone

from sqlalchemy import event

from backend.models.booking import Booking
from backend.models.guest import Guest
from backend.models.platform import Platform
from backend.models.property import Property
from backend.models.room import Room
from backend.models.room_calendar import RoomCalendar
from backend.services.gantt_service import GanttService, GanttValidationError


def seed_gantt(db):
    beta = Property(name="Beta", address="B", city="Madrid", owner="O", active=True)
    alpha = Property(name="Alpha", address="A", city="Madrid", owner="O", active=True)
    db.add_all([beta, alpha]); db.flush()
    rooms = [
        Room(property_id=beta.id, code="B-02", display_order=2, base_price=1, active=True),
        Room(property_id=alpha.id, code="A-02", display_order=2, base_price=1, active=True),
        Room(property_id=alpha.id, code="A-01", display_order=1, base_price=1, active=True),
        Room(property_id=alpha.id, code="A-X", display_order=3, base_price=1, active=False),
    ]
    db.add_all(rooms); db.flush()
    guest = Guest(full_name="Private Guest", phone="600000000", email="private@example.com")
    platform = Platform(name="Future Channel", slug="future-channel", active=True, supports_import=True, supports_export=True)
    db.add_all([guest, platform]); db.flush()
    calendar = RoomCalendar(room_id=rooms[2].id, platform_id=platform.id, import_url="https://secret.example/token.ics", active=True, automatic_sync_enabled=False)
    db.add(calendar); db.flush()
    bookings = [
        Booking(room_id=rooms[2].id, guest_id=guest.id, origin="manual", check_in=date(2026, 7, 20), check_out=date(2026, 8, 1), price=900, notes="secret"),
        Booking(room_id=rooms[2].id, room_calendar_id=calendar.id, origin="future-channel", external_reference="secret-uid", check_in=date(2026, 8, 1), check_out=date(2026, 9, 1)),
        Booking(room_id=rooms[2].id, origin="manual", check_in=date(2026, 6, 1), check_out=date(2026, 6, 15)),
    ]
    db.add_all(bookings); db.commit()
    return alpha, beta, rooms, bookings


def test_groups_orders_filters_and_intersects_half_open_window(db_session, monkeypatch):
    alpha, _, rooms, bookings = seed_gantt(db_session)
    monkeypatch.setattr("backend.services.gantt_service.business_today", lambda: date(2026, 8, 17))
    data = GanttService().get_data(db_session, date(2026, 7, 1), date(2026, 9, 1))
    assert [item.name for item in data.properties] == ["Alpha", "Beta"]
    assert [room.code for room in data.properties[0].rooms] == ["A-01", "A-02"]
    visible = data.properties[0].rooms[0].bookings
    assert [item.id for item in visible] == [bookings[0].id, bookings[1].id]
    assert visible[0].check_out == visible[1].check_in
    assert [item.lane for item in visible] == [0, 0]
    assert visible[0].editable is True and visible[1].editable is False
    assert data.properties[0].rooms[0].sync.severity == "paused"

    filtered = GanttService().get_data(db_session, date(2026, 7, 1), date(2026, 9, 1), alpha.id, True)
    assert [room.code for room in filtered.properties[0].rooms] == ["A-01", "A-02", "A-X"]


def test_historical_overlaps_use_lanes_and_operational_is_critical(db_session, monkeypatch):
    _, _, rooms, _ = seed_gantt(db_session)
    monkeypatch.setattr("backend.services.gantt_service.business_today", lambda: date(2026, 8, 17))
    db_session.add_all([
        Booking(room_id=rooms[0].id, origin="manual", check_in=date(2025, 1, 1), check_out=date(2025, 3, 1)),
        Booking(room_id=rooms[0].id, origin="manual", check_in=date(2025, 2, 1), check_out=date(2025, 2, 15)),
    ]); db_session.commit()
    data = GanttService().get_data(db_session, date(2025, 1, 1), date(2025, 4, 1))
    bars = data.properties[1].rooms[0].bookings
    assert {bar.lane for bar in bars} == {0, 1}
    assert {bar.overlap_kind for bar in bars} == {"historical"}


def test_gantt_classifies_the_shared_interval_not_each_booking_end(
    db_session, monkeypatch
):
    _, _, rooms, _ = seed_gantt(db_session)
    monkeypatch.setattr(
        "backend.services.gantt_service.business_today",
        lambda: date(2026, 7, 25),
    )
    historical_room = rooms[0]
    operational_room = rooms[1]
    db_session.add_all([
        Booking(
            room_id=historical_room.id, origin="manual",
            check_in=date(2026, 5, 8), check_out=date(2026, 8, 31),
        ),
        Booking(
            room_id=historical_room.id, origin="manual",
            check_in=date(2026, 4, 13), check_out=date(2026, 5, 31),
        ),
        Booking(
            room_id=operational_room.id, origin="manual",
            check_in=date(2026, 7, 1), check_out=date(2026, 8, 10),
        ),
        Booking(
            room_id=operational_room.id, origin="manual",
            check_in=date(2026, 7, 20), check_out=date(2026, 8, 1),
        ),
    ])
    db_session.commit()

    data = GanttService().get_data(
        db_session, date(2026, 4, 1), date(2026, 9, 1),
        include_inactive=True,
    )
    by_code = {
        room.code: room
        for property_item in data.properties
        for room in property_item.rooms
    }
    assert {
        booking.overlap_kind for booking in by_code[historical_room.code].bookings
    } == {"historical"}
    assert {
        booking.overlap_kind for booking in by_code[operational_room.code].bookings
    } == {"operational"}


def test_guest_fallback_unknown_origin_and_private_fields_are_absent(db_session):
    _, _, rooms, _ = seed_gantt(db_session)
    db_session.add(Booking(room_id=rooms[1].id, origin="new-provider", check_in=date(2027, 1, 1), check_out=date(2027, 2, 1), notes="never expose")); db_session.commit()
    payload = GanttService().get_data(db_session, date(2027, 1, 1), date(2027, 3, 1)).model_dump(mode="json")
    booking = payload["properties"][0]["rooms"][1]["bookings"][0]
    assert booking["guest_name"] == "Huésped desconocido"
    assert booking["origin"]["name"] == "New Provider"
    text = str(payload)
    assert "never expose" not in text and "external_reference" not in text
    assert "phone" not in text and "email" not in text and "price" not in text


def test_window_validation_and_default_window(monkeypatch):
    monkeypatch.setattr("backend.services.gantt_service.business_today", lambda: date(2026, 8, 17))
    assert GanttService.default_window() == (date(2026, 7, 1), date(2027, 3, 1))
    assert GanttService.default_window(date(2026, 8, 17), 4) == (date(2026, 7, 1), date(2026, 11, 1))
    assert GanttService.default_window(date(2026, 8, 17), 12) == (date(2026, 7, 1), date(2027, 7, 1))
    assert GanttService.default_window(date(2027, 3, 15)) == (date(2027, 2, 1), date(2027, 10, 1))
    assert GanttService.default_window(date(2027, 3, 15), 12) == (date(2027, 2, 1), date(2028, 2, 1))
    try: GanttService.default_window(date(2026, 8, 17), 6)
    except GanttValidationError: pass
    else: raise AssertionError("invalid scale accepted")
    for start, end in [(date(2026, 1, 1), date(2026, 1, 1)), (date(2026, 1, 2), date(2026, 1, 1)), (date(2026, 1, 1), date(2027, 1, 3))]:
        try: GanttService.validate_window(start, end)
        except GanttValidationError: pass
        else: raise AssertionError("invalid window accepted")


def test_query_count_is_constant_for_more_rooms(db_session):
    seed_gantt(db_session)
    statements = []
    def before_cursor_execute(*args): statements.append(args[2])
    event.listen(db_session.bind, "before_cursor_execute", before_cursor_execute)
    try: GanttService().get_data(db_session, date(2026, 7, 1), date(2026, 9, 1), include_inactive=True)
    finally: event.remove(db_session.bind, "before_cursor_execute", before_cursor_execute)
    selects = [statement for statement in statements if statement.lstrip().upper().startswith("SELECT")]
    assert len(selects) == 3
