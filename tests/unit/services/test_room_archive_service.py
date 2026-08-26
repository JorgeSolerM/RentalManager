from datetime import date

from backend.models.booking import Booking
from backend.models.platform import Platform
from backend.models.property import Property
from backend.models.room import Room
from backend.models.room_calendar import RoomCalendar
from backend.services.room_service import RoomService


TODAY = date(2026, 8, 26)


def make_room(db_session, *, published=True, suffix="01"):
    property_obj = Property(
        name=f"Archive property {suffix}", address="Archive address", city="Elche",
        owner="HSI", active=True,
    )
    db_session.add(property_obj)
    db_session.flush()
    room = Room(
        property_id=property_obj.id, code=f"ARCHIVE-{suffix}", display_order=1,
        base_price=475, square_meters=12, active=True,
        operational_since=TODAY,
        is_published=published, public_title="Public title",
        public_description="Public description", public_slug=f"archive-{suffix}",
    )
    db_session.add(room)
    db_session.commit()
    return room


def test_archive_empty_room_unpublishes_and_restore_does_not_republish(
    db_session, monkeypatch
):
    room = make_room(db_session)
    original = (
        room.public_title, room.public_description, room.public_slug,
        room.base_price, room.square_meters, room.operational_since,
    )
    monkeypatch.setattr("backend.services.room_service.business_today", lambda: TODAY)
    service = RoomService()

    archived = service.archive(db_session, room.id)
    restored = service.restore(db_session, room.id)

    assert archived.success and restored.success
    db_session.refresh(room)
    assert room.active is True
    assert room.is_published is False
    assert (
        room.public_title, room.public_description, room.public_slug,
        room.base_price, room.square_meters, room.operational_since,
    ) == original


def test_put_into_operation_sets_date_and_is_idempotent(db_session, monkeypatch):
    room = make_room(db_session, published=False, suffix="preparation")
    room.operational_since = None
    db_session.commit()
    monkeypatch.setattr("backend.services.room_service.business_today", lambda: TODAY)
    service = RoomService()

    first = service.put_into_operation(db_session, room.id)
    second = service.put_into_operation(db_session, room.id)

    assert first.success and second.success
    assert room.operational_since == TODAY
    assert room.active is True
    assert room.is_published is False


def test_archive_blocks_current_and_future_but_allows_contractual_history(
    db_session, monkeypatch
):
    monkeypatch.setattr("backend.services.room_service.business_today", lambda: TODAY)
    service = RoomService()

    for suffix, check_in, check_out, blocked in (
        ("history", date(2026, 7, 1), TODAY, False),
        ("current", date(2026, 8, 1), date(2026, 9, 1), True),
        ("future", date(2026, 9, 1), date(2026, 9, 30), True),
    ):
        room = make_room(db_session, suffix=suffix)
        db_session.add(Booking(
            room_id=room.id, origin="manual", external_reference=suffix,
            check_in=check_in, check_out=check_out,
        ))
        db_session.commit()

        result = service.archive(db_session, room.id)

        assert result.success is (not blocked)
        assert room.active is (True if blocked else False)
        if blocked:
            assert result.message == "room_archive_has_current_or_future_bookings"
        assert db_session.query(Booking).filter_by(room_id=room.id).count() == 1


def test_archive_preserves_calendar_configuration_and_is_idempotent(
    db_session, monkeypatch
):
    room = make_room(db_session)
    platform = Platform(
        name="Archive platform", slug="archive-platform", active=True,
        supports_import=True, supports_export=True,
    )
    db_session.add(platform)
    db_session.flush()
    calendar = RoomCalendar(
        room_id=room.id, platform_id=platform.id, active=True,
        automatic_sync_enabled=True,
        import_url="https://example.com/archive.ics",
        consecutive_failures=2,
    )
    db_session.add(calendar)
    db_session.commit()
    monkeypatch.setattr("backend.services.room_service.business_today", lambda: TODAY)
    service = RoomService()

    assert service.archive(db_session, room.id).success
    assert service.archive(db_session, room.id).success
    db_session.refresh(calendar)
    assert calendar.active is True
    assert calendar.automatic_sync_enabled is True
    assert calendar.import_url == "https://example.com/archive.ics"
    assert room.master_calendar_token
    assert calendar.consecutive_failures == 2

    assert service.restore(db_session, room.id).success
    assert service.restore(db_session, room.id).success
    db_session.refresh(calendar)
    assert calendar.automatic_sync_enabled is True
    assert calendar in service.sync_runner.repository.list_automatic_candidates(
        db_session
    )


def test_archive_rolls_back_both_lifecycle_flags_on_error(
    db_session, monkeypatch
):
    room = make_room(db_session, suffix="rollback")
    monkeypatch.setattr("backend.services.room_service.business_today", lambda: TODAY)
    service = RoomService()

    def fail_update(*_args):
        raise RuntimeError("forced failure")

    monkeypatch.setattr(service.repository, "update", fail_update)
    try:
        service.archive(db_session, room.id)
    except RuntimeError:
        pass
    else:
        raise AssertionError("archive should propagate the storage failure")

    persisted = db_session.get(Room, room.id)
    assert persisted.active is True
    assert persisted.is_published is True
