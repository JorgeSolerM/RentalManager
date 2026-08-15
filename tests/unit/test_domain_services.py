from datetime import date, timedelta

import pytest

from backend.models.booking import Booking
from backend.models.guest import Guest
from backend.models.platform import Platform
from backend.models.property import Property
from backend.models.room import Room
from backend.repositories.booking_repository import BookingRepository
from backend.repositories.guest_repository import GuestRepository
from backend.repositories.platform_repository import PlatformRepository
from backend.repositories.property_repository import PropertyRepository
from backend.repositories.room_repository import RoomRepository
from backend.services.booking_service import BookingService
from backend.services.guest_service import GuestService
from backend.services.platform_service import PlatformService
from backend.services.property_service import PropertyService
from backend.services.room_service import RoomService


def property_obj(name: str, **overrides) -> Property:
    values = {
        "name": name,
        "address": "Calle Universidad 1",
        "city": "Elche",
        "owner": "HSI Rents",
        "active": True,
    }
    values.update(overrides)
    return Property(**values)


def create_property(db_session, name: str = "Piso Universidad") -> Property:
    result = PropertyService().create_property(db_session, property_obj(name))
    assert result.success
    return result.data


def room_obj(property_id: int, code: str, display_order: int = 1) -> Room:
    return Room(
        property_id=property_id,
        code=code,
        display_order=display_order,
        base_price=350,
        active=True,
    )


def create_room(db_session, property_id: int, code: str = "H01") -> Room:
    result = RoomService().create_room(db_session, room_obj(property_id, code))
    assert result.success
    return result.data


def test_property_service_and_repository_cover_lookup_order_update_and_toggle(
    db_session,
):
    service = PropertyService()
    beta = service.create_property(db_session, property_obj("Piso Beta")).data
    alfa = service.create_property(db_session, property_obj("Piso Alfa")).data

    assert [item.name for item in service.list_properties(db_session)] == [
        "Piso Alfa",
        "Piso Beta",
    ]
    assert PropertyRepository().get_by_id(db_session, alfa.id) == alfa
    assert PropertyRepository().get_by_name(db_session, "Piso Beta") == beta

    duplicate = service.create_property(db_session, property_obj("Piso Alfa"))
    assert duplicate.success is False
    assert duplicate.message == "name_exists"

    alfa.city = "Alicante"
    assert service.update_property(db_session, alfa).success is True
    assert service.get_by_id(db_session, alfa.id).city == "Alicante"
    assert service.toggle_property(db_session, alfa).active is False


def test_property_service_rejects_delete_when_property_has_rooms(db_session):
    service = PropertyService()
    property_with_room = create_property(db_session)
    create_room(db_session, property_with_room.id)

    result = service.delete_property(db_session, property_with_room)

    assert result.success is False
    assert result.message == "property_has_rooms"
    assert service.get_by_id(db_session, property_with_room.id) is not None


def test_room_service_and_repository_cover_order_lookup_update_and_delete(db_session):
    service = RoomService()
    property_one = create_property(db_session, "Piso Uno")
    property_two = create_property(db_session, "Piso Dos")
    room_second = create_room(db_session, property_one.id, "H02")
    room_second.display_order = 2
    service.update_room(db_session, room_second)
    room_first = create_room(db_session, property_one.id, "H01")
    other_room = create_room(db_session, property_two.id, "A01")

    assert [room.code for room in service.list_rooms_by_property(
        db_session, property_one.id
    )] == ["H01", "H02"]
    assert [room.code for room in service.list_rooms(db_session)] == [
        "H01",
        "H02",
        "A01",
    ]
    assert service.count_rooms_by_property(db_session, property_one.id) == 2
    assert RoomRepository().get_by_id(db_session, room_first.id) == room_first
    assert RoomRepository().get_by_code(db_session, "A01") == other_room

    room_first.code = "H03"
    assert service.update_room(db_session, room_first).success is True
    room_second.code = "H03"
    duplicate = service.update_room(db_session, room_second)
    assert duplicate.success is False
    assert duplicate.message == "code_exists"

    assert service.delete_room(db_session, other_room).success is True
    assert service.get_room(db_session, other_room.id) is None


def test_platform_service_and_repository_cover_crud_order_and_validation(db_session):
    service = PlatformService()
    booking = service.create_platform(
        db_session,
        Platform(name="Booking.com", slug="booking", active=True),
    ).data
    airbnb = service.create_platform(
        db_session,
        Platform(name="Airbnb", slug="airbnb", active=True),
    ).data

    assert [platform.name for platform in service.list_platforms(db_session)] == [
        "Airbnb",
        "Booking.com",
    ]
    assert PlatformRepository().get_by_id(db_session, airbnb.id) == airbnb
    assert PlatformRepository().get_by_slug(db_session, "booking") == booking
    duplicate = service.create_platform(
        db_session,
        Platform(name="Otra", slug="booking", active=True),
    )
    assert duplicate.success is False
    assert duplicate.message == "slug_exists"

    updated = service.update_platform(
        db_session, airbnb.id, "Airbnb ES", "airbnb-es", True, False
    )
    assert updated.success is True
    assert updated.data.supports_import is True
    assert updated.data.supports_export is False
    assert service.update_platform(
        db_session, 999, "Ninguna", "none", False, False
    ).message == "not_found"
    assert service.delete_platform(db_session, booking.id).success is True
    assert service.delete_platform(db_session, booking.id).message == "not_found"


def test_guest_service_and_repository_trim_search_and_reuse_existing_guest(db_session):
    service = GuestService()

    guest = service.get_or_create_guest(db_session, "  Ana Pérez  ")
    existing_guest = service.get_or_create_guest(db_session, "Ana Pérez")

    assert guest.id is not None
    assert guest.full_name == "Ana Pérez"
    assert existing_guest.id == guest.id
    assert GuestRepository().get_by_id(db_session, guest.id) == guest
    assert GuestRepository().get_by_full_name(db_session, "Ana Pérez") == guest
    assert service.get_guest(db_session, 999) is None


def test_booking_service_and_repository_cover_lists_current_future_and_validation(
    db_session,
):
    room = create_room(db_session, create_property(db_session).id)
    guest = GuestService().get_or_create_guest(db_session, "Ana Pérez")
    service = BookingService()
    today = date.today()
    current = Booking(room_id=room.id)
    service.populate_booking(
        current,
        guest,
        today - timedelta(days=1),
        today + timedelta(days=1),
        100,
        "Actual",
    )
    future_later = Booking(room_id=room.id)
    service.populate_booking(
        future_later,
        guest,
        today + timedelta(days=10),
        today + timedelta(days=12),
        200,
        None,
    )
    future_earlier = Booking(room_id=room.id)
    service.populate_booking(
        future_earlier,
        guest,
        today + timedelta(days=5),
        today + timedelta(days=7),
        150,
        None,
    )
    for booking in (current, future_later, future_earlier):
        service.create_booking(db_session, booking)

    assert BookingRepository().get_by_id(db_session, current.id) == current
    assert [booking.id for booking in service.list_bookings_by_room(
        db_session, room.id
    )] == [current.id, future_earlier.id, future_later.id]
    assert service.get_current_booking(db_session, room.id).id == current.id
    assert [booking.id for booking in service.get_future_bookings(
        db_session, room.id
    )] == [future_earlier.id, future_later.id]

    current.notes = "Actualizada"
    current.price = 125
    assert service.update_booking(db_session, current).notes == "Actualizada"

    invalid = Booking(
        room_id=room.id,
        check_in=today,
        check_out=today,
        origin="manual",
    )
    with pytest.raises(ValueError, match="fecha de salida"):
        service.create_booking(db_session, invalid)
    with pytest.raises(ValueError, match="fecha de salida"):
        service.update_booking(db_session, invalid)

    service.delete_booking(db_session, current)
    assert service.get_booking(db_session, current.id) is None
