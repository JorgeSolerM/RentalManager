from datetime import date, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from backend.integrations.ical_parser import IcalParseError, IcalParser, NormalizedIcalEvent
from backend.models.booking import Booking
from backend.models.guest import Guest
from backend.models.platform import Platform
from backend.models.property import Property
from backend.models.room import Room
from backend.models.room_calendar import RoomCalendar
from backend.services.ical_sync_service import IcalSyncService


class FakeHttpClient:
    def download(self, _url):
        return b"ical"


class FakeParser:
    def __init__(self, events=None, error=None):
        self.events = events or []
        self.error = error

    def parse(self, _content):
        if self.error:
            raise self.error
        return self.events


def imported(uid, start, end, notes=None, cancelled=False, summary=None):
    return NormalizedIcalEvent(
        uid, start, end, notes, cancelled, summary=summary
    )


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
        import_url=f"https://calendar.example/{suffix}.ics", active=True,
    )
    db_session.add(calendar)
    db_session.commit()
    return room, calendar


def service_for(events=None, error=None):
    return IcalSyncService(FakeHttpClient(), FakeParser(events, error))


def ical_feed(*events):
    components = "".join(
        "BEGIN:VEVENT\r\n"
        f"UID:{uid}\r\nDTSTART;VALUE=DATE:{start}\r\n"
        f"DTEND;VALUE=DATE:{exclusive_end}\r\n"
        "END:VEVENT\r\n"
        for uid, start, exclusive_end in events
    )
    return (
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\n"
        f"{components}END:VCALENDAR\r\n"
    ).encode()


def housing_feed(uid, summary, description="Auxiliary information"):
    return (
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\n"
        f"UID:{uid}\r\nDTSTART;VALUE=DATE:20260901\r\n"
        "DTEND;VALUE=DATE:20260906\r\n"
        f"SUMMARY:{summary}\r\nDESCRIPTION:{description}\r\n"
        "END:VEVENT\r\nEND:VCALENDAR\r\n"
    ).encode()


def setup_housing_calendar(db_session):
    room, calendar = setup_calendar(db_session)
    calendar.platform.slug = "housinganywhere"
    db_session.commit()
    return room, calendar


class HousingFeedClient:
    def __init__(self, content):
        self.content = content

    def download(self, _url):
        return self.content


def test_sync_creates_idempotently_then_updates_existing_booking(db_session):
    room, calendar = setup_calendar(db_session)
    first_event = imported(
        "UID-1", date(2026, 9, 1), date(2026, 9, 5), "Guest text"
    )
    first = service_for([first_event]).synchronize(db_session, calendar.id)
    first_sync_at = calendar.last_sync_at
    second = service_for([first_event]).synchronize(db_session, calendar.id)
    moved = service_for([imported(
        "UID-1", date(2026, 9, 2), date(2026, 9, 6), "Moved"
    )]).synchronize(db_session, calendar.id)

    bookings = db_session.scalars(select(Booking)).all()
    assert first.success and first.data.created == 1
    assert second.success and second.data.unchanged == 1
    assert moved.success and moved.data.updated == 1
    assert len(bookings) == 1
    assert bookings[0].room_id == room.id
    assert bookings[0].room_calendar_id == calendar.id
    assert bookings[0].external_reference == "UID-1"
    assert bookings[0].origin == calendar.platform.slug
    assert bookings[0].guest_id is None and bookings[0].price is None
    assert bookings[0].check_in == date(2026, 9, 2)
    assert first_sync_at is not None


def test_resync_corrects_exclusive_ical_end_without_creating_booking(db_session):
    room, calendar = setup_calendar(db_session)
    existing = Booking(
        room_id=room.id,
        room_calendar_id=calendar.id,
        guest_id=None,
        origin=calendar.platform.slug,
        external_reference="105947659-2323473@housinganywhere.com",
        check_in=date(2026, 5, 8),
        check_out=date(2026, 9, 1),
    )
    second_existing = Booking(
        room_id=room.id,
        room_calendar_id=calendar.id,
        guest_id=None,
        origin=calendar.platform.slug,
        external_reference="108253599-2323473@housinganywhere.com",
        check_in=date(2026, 10, 1),
        check_out=date(2027, 3, 1),
    )
    db_session.add_all([existing, second_existing])
    db_session.commit()
    existing_ids = {existing.id, second_existing.id}

    class FeedClient:
        def download(self, _url):
            return ical_feed(
                (
                    "105947659-2323473@housinganywhere.com",
                    "20260508",
                    "20260901",
                ),
                (
                    "108253599-2323473@housinganywhere.com",
                    "20261001",
                    "20270301",
                ),
            )

    result = IcalSyncService(FeedClient(), IcalParser()).synchronize(
        db_session, calendar.id
    )

    bookings = db_session.scalars(select(Booking)).all()
    assert result.success and result.data.updated == 2
    assert result.data.created == 0
    assert len(bookings) == 2
    assert {booking.id for booking in bookings} == existing_ids
    by_reference = {booking.external_reference: booking for booking in bookings}
    assert by_reference[
        "105947659-2323473@housinganywhere.com"
    ].check_out == date(2026, 8, 31)
    assert by_reference[
        "108253599-2323473@housinganywhere.com"
    ].check_out == date(2027, 2, 28)


def test_housinganywhere_name_creates_guest_and_resync_is_idempotent(db_session):
    _room, calendar = setup_housing_calendar(db_session)
    service = IcalSyncService(
        HousingFeedClient(housing_feed("HA-1", "Reservas: Aleksandra")),
        IcalParser(),
    )

    first = service.synchronize(db_session, calendar.id)
    booking = db_session.scalar(
        select(Booking).where(Booking.external_reference == "HA-1")
    )
    booking_id = booking.id
    second = service.synchronize(db_session, calendar.id)

    guests = db_session.scalars(select(Guest)).all()
    bookings = db_session.scalars(select(Booking)).all()
    assert first.success and second.success
    assert len(guests) == 1 and guests[0].full_name == "Aleksandra"
    assert len(bookings) == 1 and bookings[0].id == booking_id
    assert bookings[0].guest_id == guests[0].id


def test_housinganywhere_reuses_existing_guest_by_normalized_name(db_session):
    _room, calendar = setup_housing_calendar(db_session)
    guest = Guest(full_name="Aleksandra", display_name="Aleksandra", active=True)
    db_session.add(guest)
    db_session.commit()

    result = IcalSyncService(
        HousingFeedClient(housing_feed("HA-REUSE", "Reservas:   Aleksandra  ")),
        IcalParser(),
    ).synchronize(db_session, calendar.id)

    booking = db_session.scalar(
        select(Booking).where(Booking.external_reference == "HA-REUSE")
    )
    assert result.success
    assert booking.guest_id == guest.id
    assert len(db_session.scalars(select(Guest)).all()) == 1


def test_housinganywhere_manual_block_does_not_create_guest(db_session):
    _room, calendar = setup_housing_calendar(db_session)
    result = IcalSyncService(
        HousingFeedClient(housing_feed(
            "HA-BLOCK", "Manualmente bloqueado", "Aleksandra in description"
        )),
        IcalParser(),
    ).synchronize(db_session, calendar.id)

    booking = db_session.scalar(
        select(Booking).where(Booking.external_reference == "HA-BLOCK")
    )
    assert result.success
    assert booking.guest_id is None
    assert db_session.scalar(select(Guest)) is None


def test_housinganywhere_ignores_imported_calendar_echo_before_overlap(
    db_session,
):
    room, calendar = setup_housing_calendar(db_session)
    manual = Booking(
        room_id=room.id,
        guest_id=None,
        origin="manual",
        check_in=date(2026, 9, 21),
        check_out=date(2026, 9, 27),
    )
    db_session.add(manual)
    db_session.commit()

    events = [
        imported(
            "111256613-2323473@housinganywhere.com",
            date(2026, 9, 21),
            date(2026, 9, 27),
            summary="Evento importado desde el archivo de calendario",
        ),
        imported(
            "HA-REAL",
            date(2026, 10, 1),
            date(2026, 10, 5),
            summary="Reservas: Aleksandra",
        ),
        imported(
            "HA-MANUAL-BLOCK",
            date(2026, 11, 1),
            date(2026, 11, 5),
            summary="Manualmente bloqueado",
        ),
    ]
    service = service_for(events)

    first = service.synchronize(db_session, calendar.id)
    second = service.synchronize(db_session, calendar.id)
    bookings = db_session.scalars(select(Booking).order_by(Booking.id)).all()

    assert first.success and first.data.created == 2
    assert first.data.ignored_echoes == 1
    assert second.success and second.data.unchanged == 2
    assert second.data.ignored_echoes == 1
    assert len(bookings) == 3
    assert db_session.get(Booking, manual.id).id == manual.id
    assert db_session.scalar(
        select(Booking).where(
            Booking.external_reference
            == "111256613-2323473@housinganywhere.com"
        )
    ) is None
    real = db_session.scalar(
        select(Booking).where(Booking.external_reference == "HA-REAL")
    )
    block = db_session.scalar(
        select(Booking).where(
            Booking.external_reference == "HA-MANUAL-BLOCK"
        )
    )
    assert real.guest.full_name == "Aleksandra"
    assert block.guest_id is None


def test_housinganywhere_echo_filter_preserves_atomic_rollback(
    db_session, monkeypatch
):
    room, calendar = setup_housing_calendar(db_session)
    manual = Booking(
        room_id=room.id,
        guest_id=None,
        origin="manual",
        check_in=date(2026, 9, 21),
        check_out=date(2026, 9, 27),
    )
    db_session.add(manual)
    db_session.commit()
    service = service_for([
        imported(
            "HA-ECHO",
            date(2026, 9, 21),
            date(2026, 9, 27),
            summary="Evento importado desde el archivo de calendario",
        ),
        imported(
            "HA-REAL",
            date(2026, 10, 1),
            date(2026, 10, 5),
            summary="Reservas: Aleksandra",
        ),
    ])

    def fail_sync_marker(_db, _calendar):
        raise RuntimeError("late failure")

    monkeypatch.setattr(service.calendar_repository, "mark_synced", fail_sync_marker)
    with pytest.raises(RuntimeError, match="late failure"):
        service.synchronize(db_session, calendar.id)

    assert db_session.get(Booking, manual.id).id == manual.id
    assert db_session.scalar(
        select(Booking).where(Booking.external_reference.is_not(None))
    ) is None
    assert db_session.scalar(select(Guest)) is None


def test_historical_flatio_booking_can_overlap_dylan_history(
    db_session, monkeypatch
):
    today = date(2026, 8, 17)
    monkeypatch.setattr(
        "backend.services.ical_sync_service.business_today", lambda: today
    )
    room, calendar = setup_calendar(db_session, "flatio-history")
    calendar.platform.slug = "flatio"
    db_session.add_all([
        Booking(
            room_id=room.id, origin="spotahome",
            check_in=date(2026, 4, 1), check_out=date(2026, 4, 30),
        ),
        Booking(
            room_id=room.id, origin="housinganywhere",
            check_in=date(2026, 5, 8), check_out=date(2026, 8, 31),
        ),
    ])
    db_session.commit()
    service = service_for([
        imported(
            "3735303139",
            date(2026, 4, 13),
            date(2026, 5, 31),
            summary="Reserved by Dylan S. (Flatio)",
        )
    ])

    first = service.synchronize(db_session, calendar.id)
    second = service.synchronize(db_session, calendar.id)
    dylan = db_session.scalar(
        select(Booking).where(Booking.external_reference == "3735303139")
    )

    assert first.success and first.data.created == 1
    assert second.success and second.data.unchanged == 1
    assert dylan.guest.full_name == "Dylan S."
    assert len(db_session.scalars(select(Booking)).all()) == 3


def test_existing_booking_guest_is_never_overwritten(db_session):
    room, calendar = setup_housing_calendar(db_session)
    maria = Guest(full_name="Maria", display_name="Maria", active=True)
    db_session.add(maria)
    db_session.flush()
    booking = Booking(
        room_id=room.id, room_calendar_id=calendar.id, guest_id=maria.id,
        origin="housinganywhere", external_reference="HA-EXISTING",
        check_in=date(2026, 9, 1), check_out=date(2026, 9, 5),
    )
    db_session.add(booking)
    db_session.commit()

    result = IcalSyncService(
        HousingFeedClient(housing_feed("HA-EXISTING", "Reservas: Aleksandra")),
        IcalParser(),
    ).synchronize(db_session, calendar.id)

    assert result.success
    assert db_session.get(Booking, booking.id).guest_id == maria.id
    assert db_session.scalar(
        select(Guest).where(Guest.full_name == "Aleksandra")
    ) is None


def test_existing_manual_guest_is_preserved_when_feed_has_no_identity(db_session):
    room, calendar = setup_calendar(db_session, "spotahome")
    calendar.platform.slug = "spotahome"
    guest = Guest(full_name="Nombre real", display_name="Nombre real", active=True)
    db_session.add(guest)
    db_session.flush()
    booking = Booking(
        room_id=room.id, room_calendar_id=calendar.id, guest_id=guest.id,
        origin="spotahome", external_reference="SPOT-35",
        check_in=date(2026, 9, 1), check_out=date(2026, 9, 5),
    )
    db_session.add(booking)
    db_session.commit()

    result = service_for([
        imported(
            "SPOT-35", date(2026, 9, 1), date(2026, 9, 5),
            summary="Spotahome",
        )
    ]).synchronize(db_session, calendar.id)

    assert result.success
    assert result.data.unchanged == 1
    assert db_session.get(Booking, booking.id).guest_id == guest.id


def test_guest_creation_rolls_back_with_failed_sync(db_session, monkeypatch):
    _room, calendar = setup_housing_calendar(db_session)
    service = IcalSyncService(
        HousingFeedClient(housing_feed("HA-ROLLBACK", "Reservas: Aleksandra")),
        IcalParser(),
    )

    def fail_sync_marker(_db, _calendar):
        raise RuntimeError("late failure")

    monkeypatch.setattr(service.calendar_repository, "mark_synced", fail_sync_marker)
    with pytest.raises(RuntimeError, match="late failure"):
        service.synchronize(db_session, calendar.id)

    assert db_session.scalar(select(Guest)) is None
    assert db_session.scalar(
        select(Booking).where(Booking.external_reference == "HA-ROLLBACK")
    ) is None
    assert db_session.scalar(select(Booking.id).limit(1)) is None


def test_cancelled_and_disappeared_bookings_are_preserved_as_warnings(db_session):
    room, calendar = setup_calendar(db_session)
    cancelled = Booking(
        room_id=room.id, room_calendar_id=calendar.id, origin="platform-one",
        external_reference="CANCEL", check_in=date(2026, 9, 1),
        check_out=date(2026, 9, 3),
    )
    disappeared = Booking(
        room_id=room.id, room_calendar_id=calendar.id, origin="platform-one",
        external_reference="GONE", check_in=date(2026, 10, 1),
        check_out=date(2026, 10, 3),
    )
    db_session.add_all([cancelled, disappeared])
    db_session.commit()

    result = service_for([
        imported("CANCEL", None, None, cancelled=True),
        imported("NEW-CANCEL", None, None, cancelled=True),
    ]).synchronize(db_session, calendar.id)

    assert result.success
    assert result.message == "room_calendar_sync_completed_with_warnings"
    assert result.data.cancelled == 2
    assert result.data.disappeared == 1
    assert db_session.get(Booking, cancelled.id) is not None
    assert db_session.get(Booking, disappeared.id) is not None
    assert db_session.scalar(
        select(Booking).where(Booking.external_reference == "NEW-CANCEL")
    ) is None


def test_same_uid_in_another_calendar_is_never_modified(db_session):
    first_room, first_calendar = setup_calendar(db_session, "one")
    second_room, second_calendar = setup_calendar(db_session, "two")
    other = Booking(
        room_id=second_room.id, room_calendar_id=second_calendar.id,
        origin="platform-two", external_reference="SAME",
        check_in=date(2026, 9, 1), check_out=date(2026, 9, 5),
    )
    db_session.add(other)
    db_session.commit()

    result = service_for([imported(
        "SAME", date(2026, 10, 1), date(2026, 10, 5)
    )]).synchronize(db_session, first_calendar.id)

    assert result.success and result.data.created == 1
    db_session.refresh(other)
    assert other.check_in == date(2026, 9, 1)
    assert len(db_session.scalars(
        select(Booking).where(Booking.external_reference == "SAME")
    ).all()) == 2


def test_overlap_with_manual_booking_rejects_every_event_and_session_is_reusable(db_session):
    room, calendar = setup_calendar(db_session)
    manual = Booking(
        room_id=room.id, room_calendar_id=None, guest_id=None, origin="manual",
        external_reference=None, check_in=date(2026, 9, 3),
        check_out=date(2026, 9, 7),
    )
    db_session.add(manual)
    db_session.commit()

    result = service_for([
        imported("SAFE", date(2026, 8, 1), date(2026, 8, 5)),
        imported("OVERLAP", date(2026, 9, 1), date(2026, 9, 5)),
    ]).synchronize(db_session, calendar.id)

    assert result.message == "room_calendar_sync_overlap"
    assert calendar.last_sync_at is None
    assert db_session.scalar(
        select(Booking).where(Booking.external_reference == "SAFE")
    ) is None
    assert db_session.scalar(select(Booking).where(Booking.id == manual.id)) is not None


def test_overlap_is_checked_after_all_day_checkout_conversion(db_session):
    room, calendar = setup_calendar(db_session)
    manual = Booking(
        room_id=room.id, room_calendar_id=None, guest_id=None, origin="manual",
        external_reference=None, check_in=date(2026, 8, 30),
        check_out=date(2026, 9, 2),
    )
    db_session.add(manual)
    db_session.commit()

    class FeedClient:
        def download(self, _url):
            return ical_feed(("OVERLAP", "20260508", "20260901"))

    result = IcalSyncService(FeedClient(), IcalParser()).synchronize(
        db_session, calendar.id
    )

    assert result.message == "room_calendar_sync_overlap"
    assert db_session.scalar(
        select(Booking).where(Booking.external_reference == "OVERLAP")
    ) is None


def test_sync_allows_overlap_whose_real_intersection_is_historical(
    db_session, monkeypatch
):
    monkeypatch.setattr(
        "backend.services.ical_sync_service.business_today",
        lambda: date(2026, 8, 17),
    )
    room, calendar = setup_calendar(db_session, "historical-intersection")
    db_session.add(Booking(
        room_id=room.id, origin="manual",
        check_in=date(2026, 4, 13), check_out=date(2026, 5, 31),
    ))
    db_session.commit()

    result = service_for([
        imported("FUTURE-TAIL", date(2026, 5, 8), date(2026, 8, 31)),
        imported("PAST-ONE", date(2026, 4, 20), date(2026, 5, 1)),
        imported("PAST-TWO", date(2026, 5, 1), date(2026, 5, 10)),
    ]).synchronize(db_session, calendar.id)

    assert result.success
    assert result.data.created == 3
    assert calendar.last_sync_at is not None


def test_historical_overlaps_do_not_hide_a_future_sync_conflict(
    db_session, monkeypatch
):
    monkeypatch.setattr(
        "backend.services.ical_sync_service.business_today",
        lambda: date(2026, 8, 17),
    )
    room, calendar = setup_calendar(db_session, "mixed-intersections")
    db_session.add_all([
        Booking(
            room_id=room.id, origin="manual",
            check_in=date(2026, 4, 13), check_out=date(2026, 5, 31),
        ),
        Booking(
            room_id=room.id, origin="manual",
            check_in=date(2026, 9, 10), check_out=date(2026, 9, 20),
        ),
    ])
    db_session.commit()

    result = service_for([
        imported("HISTORICAL", date(2026, 5, 8), date(2026, 8, 31)),
        imported("FUTURE", date(2026, 9, 15), date(2026, 9, 25)),
    ]).synchronize(db_session, calendar.id)

    assert result.message == "room_calendar_sync_overlap"
    assert calendar.last_sync_at is None
    assert db_session.scalar(
        select(Booking).where(Booking.external_reference == "HISTORICAL")
    ) is None
    assert db_session.scalar(
        select(Booking).where(Booking.external_reference == "FUTURE")
    ) is None


def test_invalid_feed_rolls_back_and_does_not_update_last_sync(db_session):
    _room, calendar = setup_calendar(db_session)
    result = service_for(error=IcalParseError()).synchronize(db_session, calendar.id)
    assert result.message == "room_calendar_sync_invalid_feed"
    assert calendar.last_sync_at is None


def test_successful_sync_tracks_present_uids_and_proves_absent_ones(db_session):
    room, calendar = setup_calendar(db_session, "presence")
    first_sync = datetime(2026, 8, 19, 10, 0)
    second_sync = datetime(2026, 8, 19, 10, 10)
    present = Booking(
        room_id=room.id, room_calendar_id=calendar.id,
        origin=calendar.platform.slug, external_reference="PRESENT",
        check_in=date(2026, 9, 1), check_out=date(2026, 9, 5),
    )
    disappeared = Booking(
        room_id=room.id, room_calendar_id=calendar.id,
        origin=calendar.platform.slug, external_reference="GONE",
        check_in=date(2026, 10, 1), check_out=date(2026, 10, 5),
    )
    db_session.add_all([present, disappeared])
    db_session.commit()
    events = [imported("PRESENT", date(2026, 9, 1), date(2026, 9, 5))]

    first = IcalSyncService(
        FakeHttpClient(), FakeParser(events), now_factory=lambda: first_sync
    ).synchronize(db_session, calendar.id)

    assert first.success
    assert calendar.feed_presence_tracking_started_at == first_sync
    assert calendar.last_sync_at == first_sync
    assert present.last_seen_in_feed_at == first_sync
    assert disappeared.last_seen_in_feed_at is None

    second = IcalSyncService(
        FakeHttpClient(), FakeParser(events), now_factory=lambda: second_sync
    ).synchronize(db_session, calendar.id)
    assert second.success
    assert calendar.feed_presence_tracking_started_at == first_sync
    assert calendar.last_sync_at == second_sync
    assert present.last_seen_in_feed_at == second_sync
    assert disappeared.last_seen_in_feed_at is None


def test_presence_tracking_rolls_back_with_late_sync_failure(db_session, monkeypatch):
    room, calendar = setup_calendar(db_session, "presence-rollback")
    booking = Booking(
        room_id=room.id, room_calendar_id=calendar.id,
        origin=calendar.platform.slug, external_reference="PRESENT",
        check_in=date(2026, 9, 1), check_out=date(2026, 9, 5),
    )
    db_session.add(booking)
    db_session.commit()
    service = IcalSyncService(
        FakeHttpClient(),
        FakeParser([imported("PRESENT", date(2026, 9, 1), date(2026, 9, 5))]),
        now_factory=lambda: datetime(2026, 8, 19, 10, 0),
    )

    def fail_marker(_db, _calendar):
        raise RuntimeError("late failure")

    monkeypatch.setattr(service.calendar_repository, "mark_synced", fail_marker)
    with pytest.raises(RuntimeError, match="late failure"):
        service.synchronize(db_session, calendar.id)

    assert db_session.get(Booking, booking.id).last_seen_in_feed_at is None
    persisted_calendar = db_session.get(RoomCalendar, calendar.id)
    assert persisted_calendar.feed_presence_tracking_started_at is None
    assert persisted_calendar.last_sync_at is None


def test_trigger_failure_during_multi_update_rolls_back_all_changes(db_session, monkeypatch):
    room, calendar = setup_calendar(db_session)
    first = Booking(
        room_id=room.id, room_calendar_id=calendar.id, origin="platform-one",
        external_reference="FIRST", check_in=date(2026, 9, 1), check_out=date(2026, 9, 3),
    )
    second = Booking(
        room_id=room.id, room_calendar_id=calendar.id, origin="platform-one",
        external_reference="SECOND", check_in=date(2026, 9, 3), check_out=date(2026, 9, 5),
    )
    db_session.add_all([first, second])
    db_session.commit()
    service = service_for([
        imported("FIRST", date(2026, 9, 3), date(2026, 9, 5)),
        imported("SECOND", date(2026, 9, 1), date(2026, 9, 3)),
    ])
    original_update = service.booking_repository.update
    calls = 0

    def fail_second(db, booking):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise IntegrityError("update", {}, Exception("booking_overlap"))
        return original_update(db, booking)

    monkeypatch.setattr(service.booking_repository, "update", fail_second)
    result = service.synchronize(db_session, calendar.id)

    assert result.message == "room_calendar_sync_overlap"
    assert db_session.get(Booking, first.id).check_in == date(2026, 9, 1)
    assert db_session.get(Booking, second.id).check_in == date(2026, 9, 3)
    assert db_session.scalar(select(Booking.id).limit(1)) is not None
