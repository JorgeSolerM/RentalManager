from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from backend.database.session import engine as application_engine
from backend.models.booking import Booking
from backend.models.guest import Guest
from backend.models.platform import Platform
from backend.models.property import Property
from backend.models.room import Room
from backend.models.room_calendar import RoomCalendar
from backend.services.platform_service import PlatformService
from backend.services.property_service import PropertyService
from backend.services.room_service import RoomService


def create_property(db_session) -> Property:
    property_obj = Property(
        name="Piso Integridad",
        address="Calle Integridad 1",
        city="Elche",
        owner="HSI Rents",
        active=True,
    )
    db_session.add(property_obj)
    db_session.flush()
    return property_obj


def create_room(db_session, property_id: int) -> Room:
    room = Room(
        property_id=property_id,
        code="I01",
        display_order=1,
        base_price=350,
        active=True,
    )
    db_session.add(room)
    db_session.flush()
    return room


def create_platform(db_session) -> Platform:
    platform = Platform(name="Integridad", slug="integridad", active=True)
    db_session.add(platform)
    db_session.flush()
    return platform


def create_booking(db_session, room_id: int, **overrides) -> Booking:
    values = {
        "room_id": room_id,
        "origin": "manual",
        "check_in": date.today(),
        "check_out": date.today() + timedelta(days=1),
    }
    values.update(overrides)
    booking = Booking(**values)
    db_session.add(booking)
    db_session.flush()
    return booking


def test_application_and_temporary_sqlite_connections_enable_foreign_keys(tmp_path):
    with application_engine.connect() as connection:
        assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1

    temporary_engine = create_engine(
        f"sqlite:///{(tmp_path / 'foreign_keys.db').as_posix()}"
    )
    try:
        with temporary_engine.connect() as connection:
            assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
    finally:
        temporary_engine.dispose()


def test_invalid_foreign_key_insert_is_rejected(db_session):
    db_session.add(
        Room(
            property_id=999,
            code="INVALID",
            display_order=1,
            base_price=350,
            active=True,
        )
    )

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_property_with_rooms_cannot_be_deleted(db_session):
    property_obj = create_property(db_session)
    create_room(db_session, property_obj.id)
    db_session.commit()

    result = PropertyService().delete_property(db_session, property_obj.id)

    assert result.success is False
    assert result.message == "property_has_rooms"


def test_room_with_booking_cannot_be_deleted(db_session):
    property_obj = create_property(db_session)
    room = create_room(db_session, property_obj.id)
    create_booking(db_session, room.id)
    db_session.commit()

    result = RoomService().delete_room(db_session, room.id)

    assert result.success is False
    assert result.message == "room_has_bookings"
    assert db_session.get(Room, room.id) is not None


def test_room_with_room_calendar_cannot_be_deleted(db_session):
    property_obj = create_property(db_session)
    room = create_room(db_session, property_obj.id)
    platform = create_platform(db_session)
    db_session.add(RoomCalendar(room_id=room.id, platform_id=platform.id, active=True))
    db_session.commit()

    result = RoomService().delete_room(db_session, room.id)

    assert result.success is False
    assert result.message == "room_has_room_calendars"


def test_platform_with_room_calendar_cannot_be_deleted(db_session):
    property_obj = create_property(db_session)
    room = create_room(db_session, property_obj.id)
    platform = create_platform(db_session)
    db_session.add(RoomCalendar(room_id=room.id, platform_id=platform.id, active=True))
    db_session.commit()

    result = PlatformService().delete_platform(db_session, platform.id)

    assert result.success is False
    assert result.message == "platform_has_room_calendars"


def test_guest_and_room_calendar_deletes_preserve_booking_relationships(db_session):
    property_obj = create_property(db_session)
    room = create_room(db_session, property_obj.id)
    platform = create_platform(db_session)
    room_calendar = RoomCalendar(
        room_id=room.id,
        platform_id=platform.id,
        active=True,
    )
    guest = Guest(full_name="Huésped", active=True)
    db_session.add_all([room_calendar, guest])
    db_session.flush()
    booking = create_booking(
        db_session,
        room.id,
        room_calendar_id=room_calendar.id,
        guest_id=guest.id,
    )
    db_session.commit()

    db_session.delete(guest)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
    assert db_session.get(Booking, booking.id).guest_id == guest.id

    db_session.delete(room_calendar)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
    assert db_session.get(Booking, booking.id).room_calendar_id == room_calendar.id


def test_inactive_room_preserves_bookings_and_room_calendars(db_session):
    property_obj = create_property(db_session)
    room = create_room(db_session, property_obj.id)
    platform = create_platform(db_session)
    room_calendar = RoomCalendar(
        room_id=room.id,
        platform_id=platform.id,
        active=True,
    )
    db_session.add(room_calendar)
    db_session.flush()
    booking = create_booking(db_session, room.id, room_calendar_id=room_calendar.id)
    room.active = False
    db_session.commit()

    persisted_room = db_session.get(Room, room.id)
    assert persisted_room.active is False
    assert db_session.get(RoomCalendar, room_calendar.id).room_id == room.id
    assert db_session.get(Booking, booking.id).room_id == room.id
