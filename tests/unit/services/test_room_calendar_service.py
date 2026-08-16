from datetime import date, datetime

import pytest
from sqlalchemy.exc import IntegrityError

from backend.models.booking import Booking
from backend.models.platform import Platform
from backend.models.property import Property
from backend.models.room import Room
from backend.models.room_calendar import RoomCalendar
from backend.services.booking_service import BookingService
from backend.services.platform_service import PlatformService
from backend.services.room_calendar_service import RoomCalendarService


def create_room(db_session, code="H01", active=True):
    property_obj = Property(
        name=f"Piso {code}", address="Calle Uno", city="Elche",
        owner="HSI", active=True,
    )
    db_session.add(property_obj)
    db_session.flush()
    room = Room(
        property_id=property_obj.id, code=code, display_order=1,
        base_price=350, active=active,
    )
    db_session.add(room)
    db_session.commit()
    return room


def create_platform(
    db_session, slug="platform", active=True,
    supports_import=True, supports_export=True,
):
    platform = Platform(
        name=slug.title(), slug=slug, active=active,
        supports_import=supports_import, supports_export=supports_export,
    )
    db_session.add(platform)
    db_session.commit()
    return platform


def create_calendar(db_session, room, platform, **overrides):
    values = {
        "import_url": "https://example.com/import.ics"
        if platform.supports_import else None,
    }
    values.update(overrides)
    result = RoomCalendarService().create_calendar(
        db_session, room.id, platform.id,
        values["import_url"],
    )
    assert result.success
    return result.data


def test_room_platform_is_unique_and_same_platform_can_configure_other_rooms(
    db_session,
):
    first_room = create_room(db_session, "H01")
    second_room = create_room(db_session, "H02")
    platform = create_platform(db_session)
    service = RoomCalendarService()
    first = create_calendar(db_session, first_room, platform)

    duplicate = service.create_calendar(
        db_session, first_room.id, platform.id,
        "https://example.com/other.ics",
    )
    second = service.create_calendar(
        db_session, second_room.id, platform.id,
        "https://example.com/second.ics",
    )

    assert duplicate.message == "room_calendar_exists"
    assert second.success
    assert first.room_id != second.data.room_id


def test_database_constraint_rejects_duplicate_room_platform(db_session):
    room = create_room(db_session)
    platform = create_platform(db_session)
    create_calendar(db_session, room, platform)
    db_session.add(RoomCalendar(room_id=room.id, platform_id=platform.id, active=True))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
    assert db_session.query(RoomCalendar).count() == 1


def test_inactive_platform_or_room_cannot_create_or_reactivate(db_session):
    active_room = create_room(db_session, "H01")
    inactive_room = create_room(db_session, "H02", active=False)
    inactive_platform = create_platform(db_session, "inactive", active=False)
    active_platform = create_platform(db_session, "active")
    service = RoomCalendarService()

    assert service.create_calendar(
        db_session, active_room.id, inactive_platform.id,
        "https://example.com/import.ics",
    ).message == "room_calendar_platform_inactive"
    assert service.create_calendar(
        db_session, inactive_room.id, active_platform.id,
        "https://example.com/import.ics",
    ).message == "room_calendar_room_inactive"

    calendar = create_calendar(db_session, active_room, active_platform)
    assert service.toggle_calendar(db_session, calendar.id).success
    active_room.active = False
    db_session.commit()
    assert service.toggle_calendar(
        db_session, calendar.id
    ).message == "room_calendar_room_inactive"
    active_room.active = True
    active_platform.active = False
    db_session.commit()
    assert service.toggle_calendar(
        db_session, calendar.id
    ).message == "room_calendar_platform_inactive"


@pytest.mark.parametrize(
    ("supports_import", "supports_export", "import_url", "message"),
    [
        (False, True, "https://example.com/in.ics", "room_calendar_import_not_supported"),
        (True, False, "", "room_calendar_import_url_required"),
        (True, True, "ftp://example.com/in.ics", "room_calendar_invalid_url"),
        (True, True, "https:///missing-host", "room_calendar_invalid_url"),
    ],
)
def test_capabilities_and_urls_are_validated(
    db_session, supports_import, supports_export, import_url, message
):
    room = create_room(db_session)
    platform = create_platform(
        db_session,
        supports_import=supports_import,
        supports_export=supports_export,
    )
    result = RoomCalendarService().create_calendar(
        db_session, room.id, platform.id, import_url
    )
    assert result.message == message


def test_update_and_toggle_preserve_urls_history_and_last_sync(db_session):
    room = create_room(db_session)
    platform = create_platform(db_session)
    calendar = create_calendar(db_session, room, platform)
    calendar.last_sync_at = datetime(2026, 8, 1, 12, 0)
    db_session.commit()
    service = RoomCalendarService()

    updated = service.update_calendar(
        db_session, calendar.id, " https://example.com/new.ics "
    )
    toggled = service.toggle_calendar(db_session, calendar.id)

    assert updated.data.import_url == "https://example.com/new.ics"
    assert updated.data.last_sync_at == datetime(2026, 8, 1, 12, 0)
    assert not toggled.data.active
    assert toggled.data.import_url == "https://example.com/new.ics"
    assert toggled.data.last_sync_at == datetime(2026, 8, 1, 12, 0)


def test_platform_capabilities_cannot_invalidate_existing_calendar(db_session):
    room = create_room(db_session)
    platform = create_platform(db_session)
    create_calendar(db_session, room, platform)
    result = PlatformService().update_platform(
        db_session, platform.id, platform.name, platform.slug, False, True
    )
    assert result.message == "platform_capabilities_in_use"
    assert db_session.get(Platform, platform.id).supports_import is True


def test_export_only_platform_can_be_configured_without_import_url(db_session):
    room = create_room(db_session)
    platform = create_platform(
        db_session, supports_import=False, supports_export=True
    )

    result = RoomCalendarService().create_calendar(
        db_session, room.id, platform.id, None
    )

    assert result.success
    assert result.data.import_url is None


def test_export_capability_can_be_reduced_without_calendar_url_data(db_session):
    room = create_room(db_session)
    platform = create_platform(
        db_session, supports_import=False, supports_export=True
    )
    create_calendar(db_session, room, platform)

    result = PlatformService().update_platform(
        db_session, platform.id, platform.name, platform.slug, False, False
    )

    assert result.success
    assert db_session.get(Platform, platform.id).supports_export is False


def test_delete_without_booking_is_allowed_but_history_blocks_delete(db_session):
    first_room = create_room(db_session, "H01")
    second_room = create_room(db_session, "H02")
    first_platform = create_platform(db_session, "first")
    second_platform = create_platform(db_session, "second")
    removable = create_calendar(db_session, first_room, first_platform)
    historical = create_calendar(db_session, second_room, second_platform)
    db_session.add(Booking(
        room_id=second_room.id,
        room_calendar_id=historical.id,
        origin="second",
        external_reference="history-1",
        check_in=date(2026, 9, 1),
        check_out=date(2026, 9, 5),
    ))
    db_session.commit()
    service = RoomCalendarService()

    blocked = service.delete_calendar(db_session, historical.id)
    deleted = service.delete_calendar(db_session, removable.id)

    assert blocked.message == "room_calendar_has_bookings"
    assert db_session.get(RoomCalendar, historical.id) is not None
    assert deleted.success
    assert db_session.get(RoomCalendar, removable.id) is None
