from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import select

from backend.models.booking import Booking
from backend.models.guest import Guest
from backend.models.platform import Platform
from backend.models.property import Property
from backend.models.room import Room
from backend.models.room_calendar import RoomCalendar
from backend.repositories.booking_repository import BookingRepository
from backend.services.booking_service import BookingService
from backend.core.business_time import business_today


def make_room(db_session, code="H01", active=True):
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


def create_manual(
    db_session, service, room_id, check_in, check_out,
    guest_name="Ana", price=100,
):
    result = service.create_manual_booking(
        db_session, room_id, guest_name, check_in, check_out, price, None
    )
    assert result.success
    return result.data


@pytest.mark.parametrize(
    ("check_in", "check_out"),
    [
        (date(2026, 9, 10), date(2026, 9, 20)),
        (date(2026, 9, 5), date(2026, 9, 15)),
        (date(2026, 9, 15), date(2026, 9, 25)),
        (date(2026, 9, 12), date(2026, 9, 18)),
        (date(2026, 9, 5), date(2026, 9, 25)),
    ],
    ids=["exact", "partial_left", "partial_right", "contained", "contains"],
)
def test_overlap_shapes_are_rejected_cleanly(db_session, check_in, check_out):
    room = make_room(db_session)
    service = BookingService()
    create_manual(
        db_session, service, room.id, date(2026, 9, 10), date(2026, 9, 20)
    )

    result = service.create_manual_booking(
        db_session, room.id, "Guest Rechazado", check_in, check_out, 100, None
    )

    assert result.message == "booking_overlap"
    assert db_session.scalar(
        select(Guest).where(Guest.full_name == "Guest Rechazado")
    ) is None
    assert len(db_session.scalars(select(Booking)).all()) == 1


def test_expected_dates_do_not_change_contractual_overlap_rules(db_session):
    room = make_room(db_session)
    service = BookingService()
    existing = create_manual(
        db_session,
        service,
        room.id,
        date(2026, 9, 10),
        date(2026, 9, 20),
    )
    existing.expected_arrival_date = date(2026, 10, 1)
    existing.expected_departure_date = date(2026, 10, 2)
    db_session.commit()

    result = service.create_manual_booking(
        db_session,
        room.id,
        "Contractual overlap",
        date(2026, 9, 12),
        date(2026, 9, 15),
        100,
        None,
    )

    assert result.message == "booking_overlap"


def test_contiguous_bookings_are_valid_on_both_boundaries(db_session):
    room = make_room(db_session)
    service = BookingService()
    create_manual(
        db_session, service, room.id, date(2026, 9, 10), date(2026, 9, 20)
    )
    before = service.create_manual_booking(
        db_session, room.id, "Antes", date(2026, 9, 5),
        date(2026, 9, 10), 100, None,
    )
    after = service.create_manual_booking(
        db_session, room.id, "Después", date(2026, 9, 20),
        date(2026, 9, 25), 100, None,
    )
    assert before.success and after.success


def test_same_dates_are_valid_in_different_rooms(db_session):
    first_room = make_room(db_session, "H01")
    second_room = make_room(db_session, "H02")
    service = BookingService()
    first = create_manual(
        db_session, service, first_room.id, date(2026, 9, 10),
        date(2026, 9, 20),
    )
    second = create_manual(
        db_session, service, second_room.id, date(2026, 9, 10),
        date(2026, 9, 20),
    )
    assert first.room_id != second.room_id


def test_repository_excludes_booking_during_overlap_check(db_session):
    room = make_room(db_session)
    service = BookingService()
    booking = create_manual(
        db_session, service, room.id, date(2026, 9, 10), date(2026, 9, 20)
    )
    repository = BookingRepository()
    assert repository.has_overlap(
        db_session, room.id, booking.check_in, booking.check_out,
        business_today(),
    )
    assert not repository.has_overlap(
        db_session, room.id, booking.check_in, booking.check_out,
        business_today(),
        exclude_booking_id=booking.id,
    )


def test_manual_historical_overlaps_can_be_created_and_edited(
    db_session, monkeypatch
):
    today = date(2026, 8, 17)
    monkeypatch.setattr(
        "backend.services.booking_service.business_today", lambda: today
    )
    room = make_room(db_session)
    service = BookingService()
    first = create_manual(
        db_session, service, room.id,
        date(2026, 4, 1), date(2026, 4, 30),
        guest_name="Historical One",
    )
    second = service.create_manual_booking(
        db_session, room.id, "Historical Two",
        date(2026, 4, 13), date(2026, 5, 31), 100, None,
    )
    assert second.success

    edited = service.update_manual_booking(
        db_session, second.data.id, "Historical Two",
        date(2026, 4, 10), date(2026, 5, 30), 100, None,
    )
    assert edited.success
    assert db_session.get(Booking, first.id) is not None


def test_overlap_ending_on_business_today_is_allowed(
    db_session, monkeypatch
):
    today = date(2026, 8, 17)
    monkeypatch.setattr(
        "backend.services.booking_service.business_today", lambda: today
    )
    room = make_room(db_session)
    service = BookingService()
    create_manual(
        db_session, service, room.id,
        date(2026, 8, 1), today,
    )

    result = service.create_manual_booking(
        db_session, room.id, "Ends Today",
        date(2026, 8, 10), date(2026, 8, 31), 100, None,
    )
    assert result.success


def test_manual_create_and_update_use_real_operational_intersection(
    db_session, monkeypatch
):
    today = date(2026, 8, 17)
    monkeypatch.setattr(
        "backend.services.booking_service.business_today", lambda: today
    )
    room = make_room(db_session)
    service = BookingService()
    historical = create_manual(
        db_session, service, room.id,
        date(2026, 4, 13), date(2026, 5, 31),
        guest_name="Historical",
    )
    future_tail = create_manual(
        db_session, service, room.id,
        date(2026, 5, 8), date(2026, 8, 31),
        guest_name="Future Tail",
    )
    assert historical.id != future_tail.id

    edit_room = make_room(db_session, "H02")
    create_manual(
        db_session, service, edit_room.id,
        date(2026, 4, 13), date(2026, 5, 31),
        guest_name="Edit Historical",
    )
    editable = create_manual(
        db_session, service, edit_room.id,
        date(2026, 9, 1), date(2026, 9, 5),
        guest_name="Editable",
    )
    edited = service.update_manual_booking(
        db_session, editable.id, "Editable",
        date(2026, 5, 10), date(2026, 8, 30), 100, None,
    )
    assert edited.success

    operational = service.create_manual_booking(
        db_session, room.id, "Operational",
        date(2026, 8, 20), date(2026, 9, 3), 100, None,
    )
    assert operational.message == "booking_overlap"


def test_edit_does_not_conflict_with_itself(db_session):
    room = make_room(db_session)
    service = BookingService()
    booking = create_manual(
        db_session, service, room.id, date(2026, 9, 10), date(2026, 9, 20)
    )
    result = service.update_manual_booking(
        db_session, booking.id, "Ana", booking.check_in,
        booking.check_out, 100, "Sin cambios de fechas",
    )
    assert result.success


def test_edit_invading_another_booking_is_rejected_without_partial_changes(db_session):
    room = make_room(db_session)
    service = BookingService()
    first = create_manual(
        db_session, service, room.id, date(2026, 9, 1), date(2026, 9, 5),
        guest_name="Primera",
    )
    create_manual(
        db_session, service, room.id, date(2026, 9, 10), date(2026, 9, 15),
        guest_name="Segunda",
    )

    result = service.update_manual_booking(
        db_session, first.id, "Guest Nuevo", date(2026, 9, 1),
        date(2026, 9, 12), 999, "No debe persistir",
    )

    assert result.message == "booking_overlap"
    persisted = db_session.get(Booking, first.id)
    assert persisted.check_out == date(2026, 9, 5)
    assert persisted.price == 100
    assert persisted.guest.full_name == "Primera"
    assert db_session.scalar(
        select(Guest).where(Guest.full_name == "Guest Nuevo")
    ) is None


def test_inactive_room_rejects_creation_and_edit_cleanly(db_session):
    room = make_room(db_session)
    service = BookingService()
    booking = create_manual(
        db_session, service, room.id, date(2026, 9, 1), date(2026, 9, 5)
    )
    room.active = False
    db_session.commit()

    creation = service.create_manual_booking(
        db_session, room.id, "Nuevo", date(2026, 9, 10),
        date(2026, 9, 15), 100, None,
    )
    update = service.update_manual_booking(
        db_session, booking.id, "Cambiado", date(2026, 9, 2),
        date(2026, 9, 6), 200, "Cambio",
    )

    assert creation.message == update.message == "booking_room_inactive"
    assert db_session.scalar(select(Guest).where(Guest.full_name == "Nuevo")) is None
    assert db_session.scalar(select(Guest).where(Guest.full_name == "Cambiado")) is None
    assert db_session.get(Booking, booking.id).check_out == date(2026, 9, 5)


@pytest.mark.parametrize("guest_name", ["", "   "])
def test_manual_guest_is_required_and_rejection_is_clean(db_session, guest_name):
    room = make_room(db_session)
    result = BookingService().create_manual_booking(
        db_session, room.id, guest_name, date(2026, 9, 1),
        date(2026, 9, 5), 100, None,
    )
    assert result.message == "booking_guest_required"
    assert db_session.scalar(select(Booking)) is None


@pytest.mark.parametrize("price", [-1, float("nan"), float("inf"), float("-inf")])
def test_invalid_monthly_prices_are_rejected_cleanly(db_session, price):
    room = make_room(db_session)
    result = BookingService().create_manual_booking(
        db_session, room.id, "Ana", date(2026, 9, 1),
        date(2026, 9, 5), price, None,
    )
    assert result.message == "booking_invalid_price"
    assert db_session.scalar(select(Guest).where(Guest.full_name == "Ana")) is None


def test_zero_monthly_price_is_valid(db_session):
    room = make_room(db_session)
    result = BookingService().create_manual_booking(
        db_session, room.id, "Ana", date(2026, 9, 1),
        date(2026, 9, 5), 0, None,
    )
    assert result.success and result.data.price == 0


@pytest.mark.parametrize(
    ("check_in", "check_out"),
    [
        (date(2026, 9, 5), date(2026, 9, 5)),
        (date(2026, 9, 6), date(2026, 9, 5)),
    ],
)
def test_equal_or_inverted_dates_are_rejected_cleanly(
    db_session, check_in, check_out
):
    room = make_room(db_session)
    result = BookingService().create_manual_booking(
        db_session, room.id, "Ana", check_in, check_out, 100, None
    )
    assert result.message == "booking_invalid_dates"
    assert db_session.scalar(select(Guest).where(Guest.full_name == "Ana")) is None


def test_missing_room_is_rejected_and_session_remains_usable(db_session):
    service = BookingService()
    result = service.create_manual_booking(
        db_session, 999, "Ana", date(2026, 9, 1),
        date(2026, 9, 5), 100, None,
    )
    assert result.message == "booking_room_not_found"
    room = make_room(db_session)
    assert create_manual(
        db_session, service, room.id, date(2026, 9, 1), date(2026, 9, 5)
    ).id is not None


def create_imported_booking_without_guest(db_session):
    room = make_room(db_session)
    platform = Platform(name="Booking.com", slug="booking", active=True)
    db_session.add(platform)
    db_session.flush()
    calendar = RoomCalendar(room_id=room.id, platform_id=platform.id, active=True)
    db_session.add(calendar)
    db_session.commit()
    booking = Booking(
        room_id=room.id,
        room_calendar_id=calendar.id,
        guest_id=None,
        origin="ical",
        check_in=date(2026, 9, 10),
        check_out=date(2026, 9, 15),
    )
    result = BookingService().create_booking(db_session, booking)
    assert result.success
    return result.data


def test_imported_booking_without_guest_is_valid_and_manual_edit_is_read_only(
    db_session,
):
    booking = create_imported_booking_without_guest(db_session)
    result = BookingService().update_manual_booking(
        db_session, booking.id, "Ana", date(2026, 9, 11),
        date(2026, 9, 16), 100, None,
    )
    assert result.message == "booking_imported_read_only"
    persisted = db_session.get(Booking, booking.id)
    assert persisted.guest_id is None
    assert persisted.check_in == date(2026, 9, 10)


def test_imported_guest_can_be_assigned_reused_changed_and_removed(db_session):
    booking = create_imported_booking_without_guest(db_session)
    service = BookingService()
    original = (
        booking.room_id, booking.room_calendar_id, booking.origin,
        booking.external_reference, booking.check_in, booking.check_out,
        booking.price,
    )
    existing = Guest(full_name="Ana Pérez", display_name="Ana Pérez", active=True)
    db_session.add(existing)
    db_session.commit()

    assigned = service.update_imported_guest(
        db_session, booking.id, "  Ana   Pérez  "
    )
    assert assigned.success
    assert assigned.data.guest_id == existing.id
    assert db_session.scalar(
        select(Guest).where(Guest.full_name == "Ana Pérez")
    ).id == existing.id

    changed = service.update_imported_guest(db_session, booking.id, "Bea López")
    assert changed.success
    assert changed.data.guest.full_name == "Bea López"

    removed = service.update_imported_guest(db_session, booking.id, "   ")
    assert removed.success
    assert removed.data.guest_id is None
    assert (
        removed.data.room_id, removed.data.room_calendar_id, removed.data.origin,
        removed.data.external_reference, removed.data.check_in,
        removed.data.check_out, removed.data.price,
    ) == original


def test_imported_guest_update_rejects_manual_booking(db_session):
    room = make_room(db_session)
    booking = create_manual(
        db_session, BookingService(), room.id,
        date(2026, 9, 1), date(2026, 9, 5),
    )

    result = BookingService().update_imported_guest(
        db_session, booking.id, "No permitido"
    )

    assert not result.success
    assert result.message == "booking_not_imported"
    assert booking.guest.full_name == "Ana"


def test_imported_guest_update_rolls_back_and_session_remains_usable(
    db_session, monkeypatch
):
    booking = create_imported_booking_without_guest(db_session)
    service = BookingService()
    original_update = service.booking_repository.update

    def fail_update(db, entity):
        original_update(db, entity)
        raise RuntimeError("forced failure")

    monkeypatch.setattr(service.booking_repository, "update", fail_update)
    with pytest.raises(RuntimeError, match="forced failure"):
        service.update_imported_guest(db_session, booking.id, "Temporal")

    assert db_session.get(Booking, booking.id).guest_id is None
    assert db_session.scalar(select(Room).where(Room.id == booking.room_id)) is not None


@pytest.mark.parametrize(
    ("check_in", "check_out"),
    [
        (date(2026, 7, 1), date(2026, 7, 15)),
        (date(2026, 8, 10), date(2026, 8, 20)),
        (date(2026, 9, 1), date(2026, 9, 15)),
    ],
    ids=["past", "current", "future"],
)
def test_manual_booking_can_always_be_deleted(
    db_session, monkeypatch, check_in, check_out
):
    monkeypatch.setattr(
        "backend.services.booking_service.business_today",
        lambda: date(2026, 8, 17),
    )
    room = make_room(db_session)
    service = BookingService()
    booking = create_manual(
        db_session, service, room.id, check_in, check_out,
        guest_name="Guest Conservado",
    )
    guest_id = booking.guest_id

    result = service.delete_booking(db_session, booking)

    assert result.success
    assert db_session.get(Booking, booking.id) is None
    assert db_session.get(Guest, guest_id) is not None


def test_manual_delete_preserves_guest_and_other_bookings(db_session):
    room = make_room(db_session)
    service = BookingService()
    deleted = create_manual(
        db_session, service, room.id, date(2026, 9, 1), date(2026, 9, 5),
        guest_name="Mismo Guest",
    )
    kept = create_manual(
        db_session, service, room.id, date(2026, 9, 5), date(2026, 9, 10),
        guest_name="Mismo Guest",
    )
    guest_id = deleted.guest_id

    assert service.delete_booking(db_session, deleted).success
    assert db_session.get(Booking, kept.id) is not None
    assert db_session.get(Guest, guest_id) is not None


def test_imported_booking_cannot_be_deleted_and_session_is_reusable(db_session):
    booking = create_imported_booking_without_guest(db_session)
    service = BookingService()

    result = service.delete_booking(db_session, booking)

    assert result.message == "booking_imported_read_only"
    assert db_session.get(Booking, booking.id) is not None
    assert db_session.scalar(select(Room).where(Room.id == booking.room_id)) is not None


def make_external_booking(db_session, slug, notes, last_seen=None, tracking=None):
    room = make_room(db_session, code=f"EXT-{slug}")
    platform = Platform(name=slug.title(), slug=slug, active=True)
    db_session.add(platform)
    db_session.flush()
    calendar = RoomCalendar(
        room_id=room.id, platform_id=platform.id, active=True,
        feed_presence_tracking_started_at=tracking,
        last_sync_at=tracking,
    )
    db_session.add(calendar)
    db_session.flush()
    guest = Guest(full_name="Conservado", display_name="Conservado", active=True)
    db_session.add(guest)
    db_session.flush()
    booking = Booking(
        room_id=room.id, room_calendar_id=calendar.id, guest_id=guest.id,
        origin=slug, external_reference="EXT-UID", notes=notes,
        check_in=date(2026, 9, 1), check_out=date(2026, 9, 5),
        last_seen_in_feed_at=last_seen,
    )
    other = Booking(
        room_id=room.id, origin="manual", guest_id=guest.id,
        check_in=date(2026, 9, 5), check_out=date(2026, 9, 10),
    )
    db_session.add_all([booking, other])
    db_session.commit()
    return booking, other, guest


def test_housing_external_block_delete_requires_demonstrated_disappearance(db_session):
    sync_at = datetime(2026, 8, 19, 10, 0)
    unknown, _, _ = make_external_booking(
        db_session, "housinganywhere", "Manualmente bloqueado"
    )
    service = BookingService()
    rejected = service.delete_booking(db_session, unknown)
    assert rejected.message == "booking_external_block_presence_unknown"

    unknown.room_calendar.feed_presence_tracking_started_at = sync_at
    unknown.room_calendar.last_sync_at = sync_at
    unknown.last_seen_in_feed_at = sync_at
    db_session.commit()
    present = service.delete_booking(db_session, unknown)
    assert present.message == "booking_external_block_still_present"

    unknown.last_seen_in_feed_at = sync_at - timedelta(minutes=1)
    db_session.commit()
    deleted = service.delete_booking(db_session, unknown)
    assert deleted.success
    assert deleted.message == "booking_external_block_deleted"


def test_disappeared_external_block_delete_preserves_guest_and_other_booking(db_session):
    sync_at = datetime(2026, 8, 19, 10, 0)
    booking, other, guest = make_external_booking(
        db_session, "housinganywhere", "Manualmente bloqueado", tracking=sync_at
    )

    result = BookingService().delete_booking(db_session, booking)

    assert result.success
    assert db_session.get(Booking, booking.id) is None
    assert db_session.get(Booking, other.id) is not None
    assert db_session.get(Guest, guest.id) is not None


@pytest.mark.parametrize(
    ("slug", "notes"),
    [
        ("housinganywhere", "Reservas: Ana"),
        ("flatio", "Reserved by Dylan (Flatio)"),
        ("spotahome", "Spotahome"),
    ],
)
def test_commercial_or_unclassified_imports_remain_non_deletable(
    db_session, slug, notes
):
    sync_at = datetime(2026, 8, 19, 10, 0)
    booking, _, _ = make_external_booking(
        db_session, slug, notes, tracking=sync_at
    )

    result = BookingService().delete_booking(db_session, booking)

    assert result.message == "booking_imported_read_only"
    assert db_session.get(Booking, booking.id) is not None
