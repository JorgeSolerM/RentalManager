from datetime import date, datetime, timedelta
from types import SimpleNamespace

from sqlalchemy import event

from backend.models.booking import Booking
from backend.models.guest import Guest
from backend.models.platform import Platform
from backend.models.property import Property
from backend.models.room import Room
from backend.models.room_calendar import RoomCalendar
from backend.services.dashboard_service import DashboardService


TODAY = date(2026, 8, 19)
NOW = datetime(2026, 8, 19, 12, 0)


def ns(**values):
    return SimpleNamespace(**values)


class FakeRepository:
    def __init__(self, rooms, bookings, calendars, overlaps):
        self.rooms = rooms
        self.bookings = bookings
        self.calendars = calendars
        self.overlaps = overlaps
        self.calls = []

    def list_operational_rooms(self, _db):
        self.calls.append("rooms")
        return self.rooms

    def list_operational_bookings(
        self, _db, today, availability_end, movement_end
    ):
        self.calls.append(("bookings", today, availability_end, movement_end))
        return self.bookings

    def list_room_calendars(self, _db):
        self.calls.append("calendars")
        return self.calendars

    def list_operational_overlaps(self, _db, today):
        self.calls.append(("overlaps", today))
        return self.overlaps


class FakeSyncRunner:
    def health_state(self, calendar, now=None):
        return calendar.health


def room(room_id, code, property_name="Property", display_order=None):
    return ns(
        id=room_id, code=code, display_order=(display_order or room_id),
        property=ns(name=property_name),
    )


def booking(
    booking_id,
    room_obj,
    check_in,
    check_out,
    guest_name="Guest",
    expected_arrival_date=None,
    expected_departure_date=None,
):
    return ns(
        id=booking_id, room_id=room_obj.id, room=room_obj,
        check_in=check_in, check_out=check_out,
        expected_arrival_date=expected_arrival_date,
        expected_departure_date=expected_departure_date,
        effective_arrival_date=expected_arrival_date or check_in,
        effective_departure_date=expected_departure_date or check_out,
        guest_id=(booking_id if guest_name is not None else None),
        guest=(ns(full_name=guest_name) if guest_name is not None else None),
        room_calendar_id=None, room_calendar=None, origin="manual",
    )


def calendar(calendar_id, room_obj, platform, health, **observation):
    defaults = {
        "master_calendar_first_request_at": None,
        "last_master_calendar_request_at": None,
        "master_calendar_request_count": 0,
        "last_sync_at": None,
    }
    defaults.update(observation)
    return ns(
        id=calendar_id, room_id=room_obj.id, room=room_obj,
        platform=platform, active=True, import_url="https://example.com/feed.ics",
        health=health, **defaults,
    )


def test_dashboard_builds_operational_summary_windows_and_real_availability():
    rooms = [room(1, "R1"), room(2, "R2"), room(3, "R3"), room(4, "R4")]
    bookings = [
        booking(1, rooms[0], TODAY - timedelta(days=4), TODAY + timedelta(days=1), None),
        booking(2, rooms[0], TODAY + timedelta(days=3), TODAY + timedelta(days=6)),
        booking(3, rooms[1], TODAY, TODAY + timedelta(days=5), None),
        booking(4, rooms[2], TODAY + timedelta(days=13), TODAY + timedelta(days=20)),
        booking(5, rooms[2], TODAY + timedelta(days=14), TODAY + timedelta(days=21)),
        booking(6, rooms[3], TODAY - timedelta(days=3), TODAY),
    ]
    imported_platform = ns(
        slug="housinganywhere", name="HousingAnywhere", favicon=None
    )
    bookings[2].room_calendar_id = 99
    bookings[2].room_calendar = ns(platform=imported_platform)
    repository = FakeRepository(rooms, bookings, [], [])
    data = DashboardService(
        repository, FakeSyncRunner(), lambda: NOW
    ).get_dashboard(None, TODAY)

    assert data.summary.active_rooms == 4
    assert data.summary.occupied_rooms == 2
    assert data.summary.free_rooms == 2
    assert data.summary.occupancy_percentage == 50
    assert data.summary.arrivals_today == 1
    assert data.summary.departures_today == 1
    assert [item.booking_id for item in data.upcoming_arrivals] == [3, 2, 4, 5]
    assert data.upcoming_arrivals[0].imported is True
    assert data.upcoming_arrivals[0].origin_name == "HousingAnywhere"
    assert next(item for item in data.upcoming_arrivals if item.booking_id == 2).imported is False
    assert data.upcoming_availability[0].available_from == TODAY + timedelta(days=1)
    assert data.upcoming_availability[0].available_until == TODAY + timedelta(days=3)
    assert {item.booking_id for item in data.incidents if item.kind == "unknown_guest"} == {1, 3}
    assert [call if isinstance(call, str) else call[0] for call in repository.calls] == [
        "rooms", "bookings", "calendars", "overlaps"
    ]


def test_occupancy_summary_handles_zero_full_and_no_active_rooms():
    first = room(1, "R1")
    second = room(2, "R2")
    occupied = [
        booking(1, first, TODAY - timedelta(days=1), TODAY + timedelta(days=1)),
        booking(2, second, TODAY, TODAY + timedelta(days=2)),
    ]
    service = lambda rooms, bookings: DashboardService(
        FakeRepository(rooms, bookings, [], []),
        FakeSyncRunner(), lambda: NOW,
    ).get_dashboard(None, TODAY).summary

    empty = service([first, second], [])
    full = service([first, second], occupied)
    no_rooms = service([], [])

    assert (empty.occupied_rooms, empty.free_rooms, empty.occupancy_percentage) == (0, 2, 0)
    assert (full.occupied_rooms, full.free_rooms, full.occupancy_percentage) == (2, 0, 100)
    assert (no_rooms.active_rooms, no_rooms.free_rooms, no_rooms.occupancy_percentage) == (0, 0, 0)


def test_movement_window_includes_day_fourteen_excludes_day_fifteen_and_is_stable():
    later_order = room(1, "A", "Same", display_order=2)
    earlier_order = room(2, "Z", "Same", display_order=1)
    bookings = [
        booking(1, later_order, TODAY + timedelta(days=14), TODAY + timedelta(days=20)),
        booking(2, earlier_order, TODAY + timedelta(days=14), TODAY + timedelta(days=20)),
        booking(3, earlier_order, TODAY + timedelta(days=15), TODAY + timedelta(days=21)),
    ]
    data = DashboardService(
        FakeRepository([later_order, earlier_order], bookings, [], []),
        FakeSyncRunner(), lambda: NOW,
    ).get_dashboard(None, TODAY)
    assert [item.booking_id for item in data.upcoming_arrivals] == [2, 1]


def test_movement_days_remaining_use_arrival_and_departure_dates():
    target = room(1, "R1")
    bookings = [
        booking(1, target, TODAY, TODAY + timedelta(days=1)),
        booking(2, target, TODAY + timedelta(days=1), TODAY + timedelta(days=4)),
        booking(3, target, TODAY + timedelta(days=3), TODAY + timedelta(days=6)),
    ]
    data = DashboardService(
        FakeRepository([target], bookings, [], []),
        FakeSyncRunner(), lambda: NOW,
    ).get_dashboard(None, TODAY)

    assert [item.days_remaining for item in data.upcoming_arrivals] == [0, 1, 3]
    assert [item.days_remaining for item in data.upcoming_departures] == [1, 4, 6]


def test_dashboard_uses_expected_dates_only_for_operational_movements():
    target = room(1, "R1")
    moved = booking(
        1,
        target,
        TODAY,
        TODAY + timedelta(days=10),
        expected_arrival_date=TODAY + timedelta(days=1),
        expected_departure_date=TODAY + timedelta(days=3),
    )
    fallback = booking(
        2,
        target,
        TODAY + timedelta(days=4),
        TODAY + timedelta(days=6),
    )
    data = DashboardService(
        FakeRepository([target], [moved, fallback], [], []),
        FakeSyncRunner(), lambda: NOW,
    ).get_dashboard(None, TODAY)

    assert [(item.booking_id, item.date, item.days_remaining) for item in data.upcoming_arrivals] == [
        (1, TODAY + timedelta(days=1), 1),
        (2, TODAY + timedelta(days=4), 4),
    ]
    assert [(item.booking_id, item.date, item.days_remaining) for item in data.upcoming_departures] == [
        (1, TODAY + timedelta(days=3), 3),
        (2, TODAY + timedelta(days=6), 6),
    ]
    assert data.summary.occupied_rooms == 1
    assert data.upcoming_availability[0].available_from == TODAY + timedelta(days=10)


def test_contiguous_reservations_are_merged_before_reporting_availability():
    target = room(1, "R1")
    bookings = [
        booking(1, target, TODAY - timedelta(days=2), TODAY + timedelta(days=2)),
        booking(2, target, TODAY + timedelta(days=2), TODAY + timedelta(days=7)),
        booking(3, target, TODAY + timedelta(days=7), TODAY + timedelta(days=31)),
    ]
    data = DashboardService(
        FakeRepository([target], bookings, [], []),
        FakeSyncRunner(), lambda: NOW,
    ).get_dashboard(None, TODAY)
    assert data.upcoming_availability == []


def test_incidents_are_prioritized_deduplicated_and_master_noise_is_excluded():
    first = room(1, "R1")
    second = room(2, "R2")
    platform = ns(slug="platform", name="Platform", favicon=None)
    stale = calendar(
        4, second, platform, "ok",
        master_calendar_first_request_at=NOW - timedelta(days=4),
        last_master_calendar_request_at=NOW - timedelta(days=3),
        master_calendar_request_count=3,
    )
    calendars = [
        calendar(1, first, platform, "error"),
        calendar(2, second, platform, "paused"),
        calendar(3, second, platform, "overdue"),
        stale,
        calendar(
            5, first, platform, "ok",
            master_calendar_first_request_at=NOW,
            last_master_calendar_request_at=NOW,
            master_calendar_request_count=1,
        ),
    ]
    overlap = {
        "first_booking_id": 10, "second_booking_id": 11,
        "room_id": first.id, "room_code": first.code,
        "property_name": "Property",
        "first_check_in": TODAY, "first_check_out": TODAY + timedelta(days=5),
        "second_check_in": TODAY + timedelta(days=1),
        "second_check_out": TODAY + timedelta(days=3),
    }
    data = DashboardService(
        FakeRepository([first, second], [], calendars, [overlap]),
        FakeSyncRunner(), lambda: NOW,
    ).get_dashboard(None, TODAY)
    severities = [item.severity for item in data.incidents]
    assert severities == sorted(severities, key={"critical": 0, "attention": 1, "informational": 2}.get)
    assert {item.kind for item in data.incidents} == {
        "operational_overlap", "calendar_error", "calendar_paused",
        "calendar_overdue", "master_calendar_stale",
    }
    assert len({item.key for item in data.incidents}) == len(data.incidents)
    summary = data.platforms[0]
    assert summary.correct == 2 and summary.review == 3


def test_reliable_last_update_uses_oldest_currently_correct_integration_only():
    target = room(1, "R1")
    platform = ns(slug="platform", name="Platform", favicon=None)
    oldest = datetime(2026, 8, 19, 9, 5)
    newest = datetime(2026, 8, 19, 10, 40)
    calendars = [
        calendar(1, target, platform, "ok", last_sync_at=newest),
        calendar(2, target, platform, "ok", last_sync_at=oldest),
        calendar(3, target, platform, "error", last_sync_at=datetime(2026, 8, 18, 8, 0)),
        calendar(4, target, platform, "overdue", last_sync_at=datetime(2026, 8, 17, 8, 0)),
        calendar(5, target, platform, "paused", last_sync_at=datetime(2026, 8, 16, 8, 0)),
    ]
    data = DashboardService(
        FakeRepository([target], [], calendars, []),
        FakeSyncRunner(), lambda: NOW,
    ).get_dashboard(None, TODAY)

    assert data.reliable_last_update == oldest
    assert data.platforms[0].correct == 2
    assert data.platforms[0].review == 3


def test_reliable_last_update_handles_one_or_no_correct_integrations():
    target = room(1, "R1")
    platform = ns(slug="platform", name="Platform", favicon=None)
    successful_at = datetime(2026, 8, 19, 11, 15)
    one_correct = DashboardService(
        FakeRepository(
            [target], [],
            [
                calendar(1, target, platform, "ok", last_sync_at=successful_at),
                calendar(2, target, platform, "error", last_sync_at=NOW),
            ],
            [],
        ),
        FakeSyncRunner(), lambda: NOW,
    ).get_dashboard(None, TODAY)
    none_correct = DashboardService(
        FakeRepository(
            [target], [],
            [calendar(3, target, platform, "paused", last_sync_at=NOW)],
            [],
        ),
        FakeSyncRunner(), lambda: NOW,
    ).get_dashboard(None, TODAY)

    assert one_correct.reliable_last_update == successful_at
    assert none_correct.reliable_last_update is None


def test_repository_backed_dashboard_keeps_four_selects_with_more_rooms(
    db_session
):
    property_obj = Property(
        name="Dashboard Property", address="A", city="Madrid", owner="O", active=True
    )
    platform = Platform(
        name="Platform", slug="dashboard-platform", active=True,
        supports_import=True, supports_export=True,
    )
    db_session.add_all([property_obj, platform]); db_session.flush()
    for index in range(12):
        room_obj = Room(
            property_id=property_obj.id, code=f"D-{index:02}",
            display_order=index, base_price=500, active=True,
            operational_since=TODAY,
        )
        db_session.add(room_obj); db_session.flush()
        if index < 3:
            guest = Guest(full_name=f"Guest {index}", active=True)
            db_session.add(guest); db_session.flush()
            db_session.add(Booking(
                room_id=room_obj.id, guest_id=guest.id, origin="manual",
                check_in=TODAY + timedelta(days=index),
                check_out=TODAY + timedelta(days=index + 1),
            ))
        db_session.add(RoomCalendar(
            room_id=room_obj.id, platform_id=platform.id,
            import_url="https://example.com/feed.ics", active=True,
            automatic_sync_enabled=False,
        ))
    db_session.commit()

    statements = []
    def record(*args):
        if args[2].lstrip().upper().startswith("SELECT"):
            statements.append(args[2])
    event.listen(db_session.bind, "before_cursor_execute", record)
    try:
        DashboardService(now_factory=lambda: NOW).get_dashboard(db_session, TODAY)
    finally:
        event.remove(db_session.bind, "before_cursor_execute", record)
    assert len(statements) == 4


def test_repository_includes_movement_outside_contractual_query_window(db_session):
    property_obj = Property(
        name="Operational Dates", address="A", city="Madrid", owner="O", active=True
    )
    room_obj = Room(
        property=property_obj, code="OP-1", display_order=1,
        base_price=500, active=True, operational_since=TODAY,
    )
    booking_obj = Booking(
        room=room_obj,
        origin="manual",
        check_in=TODAY + timedelta(days=40),
        check_out=TODAY + timedelta(days=50),
        expected_arrival_date=TODAY + timedelta(days=5),
    )
    db_session.add_all([property_obj, room_obj, booking_obj])
    db_session.commit()

    data = DashboardService(now_factory=lambda: NOW).get_dashboard(
        db_session, TODAY
    )

    assert [(item.booking_id, item.date) for item in data.upcoming_arrivals] == [
        (booking_obj.id, TODAY + timedelta(days=5))
    ]
    assert data.summary.occupied_rooms == 0


def test_repository_excludes_inactive_rooms_and_historical_overlap_incidents(
    db_session
):
    property_obj = Property(
        name="Active Filter", address="A", city="Madrid", owner="O", active=True
    )
    db_session.add(property_obj); db_session.flush()
    active = Room(
        property_id=property_obj.id, code="ACTIVE", display_order=1,
        base_price=500, active=True, operational_since=TODAY,
    )
    inactive = Room(
        property_id=property_obj.id, code="INACTIVE", display_order=2,
        base_price=500, active=False, operational_since=TODAY,
    )
    db_session.add_all([active, inactive]); db_session.flush()
    db_session.add_all([
        Booking(
            room_id=active.id, origin="manual",
            check_in=date(2026, 4, 1), check_out=date(2026, 5, 1),
        ),
        Booking(
            room_id=active.id, origin="manual",
            check_in=date(2026, 4, 15), check_out=date(2026, 5, 15),
        ),
        Booking(
            room_id=inactive.id, origin="manual",
            check_in=TODAY - timedelta(days=1), check_out=TODAY + timedelta(days=2),
        ),
    ])
    db_session.commit()

    data = DashboardService(now_factory=lambda: NOW).get_dashboard(
        db_session, TODAY
    )
    assert data.summary.active_rooms == 1
    assert data.summary.occupied_rooms == 0
    assert not any(
        item.kind == "operational_overlap" for item in data.incidents
    )
