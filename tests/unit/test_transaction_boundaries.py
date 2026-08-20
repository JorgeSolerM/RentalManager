from datetime import date
import sqlite3
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from backend.models.booking import Booking
from backend.models.guest import Guest
from backend.models.platform import Platform
from backend.models.property import Property
from backend.models.room import Room
from backend.repositories.base_repository import BaseRepository
from backend.services.booking_service import BookingService
from backend.services.platform_service import PlatformService
from backend.services.property_service import PropertyService
from backend.services.room_service import RoomService


def make_property(name="Piso Uno"):
    return Property(
        name=name, address="Calle Uno", city="Elche", owner="HSI", active=True
    )


def persist_room(db_session):
    property_obj = make_property()
    db_session.add(property_obj)
    db_session.flush()
    room = Room(
        property_id=property_obj.id, code="H01", display_order=1,
        base_price=350, active=True,
    )
    db_session.add(room)
    db_session.commit()
    return room


def test_base_repository_only_flushes_writes():
    db = MagicMock()
    repository = BaseRepository()
    first, second, third = object(), object(), object()

    assert repository.create(db, first) is first
    assert repository.update(db, second) is second
    repository.delete(db, third)

    assert db.flush.call_count == 3
    db.commit.assert_not_called()
    db.rollback.assert_not_called()
    db.refresh.assert_not_called()


def test_new_guest_and_booking_are_committed_together_and_existing_guest_is_reused(
    db_session,
):
    room = persist_room(db_session)
    service = BookingService()
    first = service.create_manual_booking(
        db_session, room.id, "Ana Pérez", date(2026, 9, 1),
        date(2026, 9, 3), 200, None,
    )
    second = service.create_manual_booking(
        db_session, room.id, "Ana Pérez", date(2026, 9, 4),
        date(2026, 9, 6), 220, None,
    )

    guests = db_session.scalars(select(Guest)).all()
    assert len(guests) == 1
    assert first.data.guest_id == second.data.guest_id == guests[0].id
    assert len(db_session.scalars(select(Booking)).all()) == 2


def test_failed_booking_creation_rolls_back_new_guest(db_session, monkeypatch):
    room = persist_room(db_session)
    service = BookingService()

    def fail_booking(*_args, **_kwargs):
        raise RuntimeError("booking write failed")

    monkeypatch.setattr(service.booking_repository, "create", fail_booking)
    with pytest.raises(RuntimeError, match="booking write failed"):
        service.create_manual_booking(
            db_session, room.id, "Guest Parcial", date(2026, 9, 1),
            date(2026, 9, 3), None, None,
        )

    assert db_session.scalar(
        select(Guest).where(Guest.full_name == "Guest Parcial")
    ) is None


def test_missing_room_rejection_rolls_back_and_session_can_be_reused(db_session):
    service = BookingService()
    result = service.create_manual_booking(
        db_session, 999, "Guest FK", date(2026, 9, 1),
        date(2026, 9, 3), None, None,
    )
    assert result.message == "booking_room_not_found"
    assert db_session.scalar(select(Guest).where(Guest.full_name == "Guest FK")) is None

    room = persist_room(db_session)
    booking = service.create_manual_booking(
        db_session, room.id, "Guest Válido", date(2026, 9, 1),
        date(2026, 9, 3), None, None,
    )
    assert booking.data.id is not None


def test_failed_booking_update_leaves_no_guest_or_partial_changes(
    db_session, monkeypatch
):
    room = persist_room(db_session)
    service = BookingService()
    booking = service.create_manual_booking(
        db_session, room.id, "Original", date(2026, 9, 1),
        date(2026, 9, 3), 100, "Original",
    )

    def fail_update(*_args, **_kwargs):
        raise RuntimeError("update failed")

    monkeypatch.setattr(service.booking_repository, "update", fail_update)
    with pytest.raises(RuntimeError, match="update failed"):
        service.update_manual_booking(
            db_session, booking.data.id, "Guest Nuevo", date(2026, 10, 1),
            date(2026, 10, 3), 999, "Cambiada",
        )

    persisted = db_session.get(Booking, booking.data.id)
    assert persisted.notes == "Original"
    assert persisted.price == 100
    assert persisted.guest.full_name == "Original"
    assert db_session.scalar(
        select(Guest).where(Guest.full_name == "Guest Nuevo")
    ) is None


@pytest.mark.parametrize("service_kind", ["property", "room", "platform"])
def test_failed_entity_update_restores_previous_values(
    db_session, monkeypatch, service_kind
):
    room = persist_room(db_session)
    if service_kind == "property":
        service = PropertyService()
        entity = db_session.get(Property, room.property_id)
        monkeypatch.setattr(service.repository, "update", MagicMock(side_effect=RuntimeError))
        call = lambda: service.update_property(
            db_session, entity.id, "Cambiada", None, entity.address,
            entity.city, entity.owner, entity.notes,
        )
        expected = lambda: db_session.get(Property, entity.id).name == "Piso Uno"
    elif service_kind == "room":
        service = RoomService()
        entity = room
        monkeypatch.setattr(service.repository, "update", MagicMock(side_effect=RuntimeError))
        call = lambda: service.update_room(db_session, entity.id, "OTRA")
        expected = lambda: db_session.get(Room, entity.id).code == "H01"
    else:
        service = PlatformService()
        entity = service.create_platform(
            db_session, Platform(name="Booking", slug="booking", active=True)
        ).data
        monkeypatch.setattr(service.repository, "update", MagicMock(side_effect=RuntimeError))
        call = lambda: service.update_platform(
            db_session, entity.id, "Cambiada", "cambiada", True, True
        )
        expected = lambda: db_session.get(Platform, entity.id).name == "Booking"

    with pytest.raises(RuntimeError):
        call()
    assert expected()


def test_blocked_delete_has_no_partial_changes(db_session):
    room = persist_room(db_session)
    result = PropertyService().delete_property(db_session, room.property_id)
    assert result.message == "property_has_rooms"
    assert db_session.get(Property, room.property_id) is not None
    assert db_session.get(Room, room.id) is not None


def test_integrity_error_during_delete_rolls_back_and_session_is_reusable(
    db_session, monkeypatch
):
    room = persist_room(db_session)
    service = PropertyService()
    monkeypatch.setattr(service.room_service, "count_rooms_by_property", lambda *_: 0)

    with pytest.raises(IntegrityError):
        service.delete_property(db_session, room.property_id)

    assert db_session.get(Property, room.property_id) is not None
    created = service.create_property(db_session, make_property("Piso Dos"))
    assert created.success and created.data.id is not None


def test_database_overlap_error_is_translated_and_session_remains_usable(
    db_session, monkeypatch
):
    room = persist_room(db_session)
    service = BookingService()

    def trigger_overlap(*_args, **_kwargs):
        raise IntegrityError(
            "INSERT INTO bookings",
            {},
            sqlite3.IntegrityError("booking_overlap"),
        )

    monkeypatch.setattr(service.booking_repository, "create", trigger_overlap)
    result = service.create_manual_booking(
        db_session, room.id, "Ana", date(2026, 9, 1),
        date(2026, 9, 5), 100, None,
    )
    assert result.message == "booking_overlap"
    assert db_session.scalar(select(Guest).where(Guest.full_name == "Ana")) is None
    assert db_session.get(Room, room.id) is not None


def test_failed_manual_booking_delete_rolls_back_and_session_is_reusable(
    db_session, monkeypatch
):
    room = persist_room(db_session)
    service = BookingService()
    booking = service.create_manual_booking(
        db_session, room.id, "Delete Rollback", date(2026, 9, 1),
        date(2026, 9, 3), None, None,
    ).data

    def fail_delete(db, entity):
        db.delete(entity)
        db.flush()
        raise RuntimeError("delete failed")

    monkeypatch.setattr(service.booking_repository, "delete", fail_delete)
    with pytest.raises(RuntimeError, match="delete failed"):
        service.delete_booking(db_session, booking)

    assert db_session.get(Booking, booking.id) is not None
    assert db_session.get(Room, room.id) is not None
