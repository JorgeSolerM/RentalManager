from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from backend.models.booking import Booking
from backend.models.platform import Platform
from backend.models.property import Property
from backend.models.room import Room
from backend.models.room_calendar import RoomCalendar
from backend.services.booking_service import BookingService


def setup_calendar(db_session, suffix="one"):
    property_obj = Property(
        name=f"Piso {suffix}", address="Calle Uno", city="Elche",
        owner="HSI", active=True,
    )
    db_session.add(property_obj)
    db_session.flush()
    room = Room(
        property_id=property_obj.id, code=f"H-{suffix}", display_order=1,
        base_price=350, active=True,
    )
    platform = Platform(
        name=f"Platform {suffix}", slug=f"platform-{suffix}", active=True,
        supports_import=True, supports_export=False,
    )
    db_session.add_all([room, platform])
    db_session.flush()
    calendar = RoomCalendar(
        room_id=room.id, platform_id=platform.id,
        import_url=f"https://example.com/{suffix}.ics", active=True,
    )
    db_session.add(calendar)
    db_session.commit()
    return room, calendar


def test_new_import_requires_non_empty_stable_reference(db_session):
    _room, calendar = setup_calendar(db_session)
    service = BookingService()
    for reference in ("", "   "):
        result = service.upsert_imported_booking(
            db_session, calendar.id, reference,
            date(2026, 9, 1), date(2026, 9, 5),
        )
        assert result.message == "booking_external_reference_required"
    assert db_session.scalar(select(Booking)) is None


def test_repeating_reference_updates_same_booking_and_preserves_case(db_session):
    _room, calendar = setup_calendar(db_session)
    service = BookingService()
    first = service.upsert_imported_booking(
        db_session, calendar.id, "  UID-AbC  ",
        date(2026, 9, 1), date(2026, 9, 5), notes="Primera",
    )
    second = service.upsert_imported_booking(
        db_session, calendar.id, "UID-AbC",
        date(2026, 9, 2), date(2026, 9, 6), notes="Actualizada",
    )

    assert first.success and second.success
    assert first.data.id == second.data.id
    assert second.data.external_reference == "UID-AbC"
    assert second.data.notes == "Actualizada"
    assert len(db_session.scalars(select(Booking)).all()) == 1


def test_same_reference_in_different_calendars_is_isolated(db_session):
    _first_room, first_calendar = setup_calendar(db_session, "one")
    _second_room, second_calendar = setup_calendar(db_session, "two")
    service = BookingService()
    first = service.upsert_imported_booking(
        db_session, first_calendar.id, "SAME-UID",
        date(2026, 9, 1), date(2026, 9, 5),
    )
    second = service.upsert_imported_booking(
        db_session, second_calendar.id, "SAME-UID",
        date(2026, 9, 1), date(2026, 9, 5),
    )
    assert first.success and second.success
    assert first.data.id != second.data.id
    assert first.data.room_calendar_id != second.data.room_calendar_id


def test_partial_unique_index_rejects_duplicate_but_allows_historical_nulls(
    db_session,
):
    room, calendar = setup_calendar(db_session)
    values = dict(
        room_id=room.id,
        room_calendar_id=calendar.id,
        origin="platform-one",
        check_in=date(2026, 9, 1),
        check_out=date(2026, 9, 5),
    )
    db_session.add(Booking(**values, external_reference="DUP"))
    db_session.commit()
    db_session.add(Booking(**{
        **values,
        "external_reference": "DUP",
        "check_in": date(2026, 10, 1),
        "check_out": date(2026, 10, 5),
    }))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    db_session.add_all([
        Booking(**{
            **values,
            "external_reference": None,
            "check_in": date(2026, 11, 1),
            "check_out": date(2026, 11, 5),
        }),
        Booking(**{
            **values,
            "external_reference": None,
            "check_in": date(2026, 12, 1),
            "check_out": date(2026, 12, 5),
        }),
    ])
    db_session.commit()
    assert len(db_session.scalars(
        select(Booking).where(Booking.external_reference.is_(None))
    ).all()) == 2
