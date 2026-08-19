import sqlite3
import threading
from datetime import date
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import backend.database.session as database_session
from backend.database.session import register_sqlite_functions
from backend.integrations.ical_parser import NormalizedIcalEvent
from backend.models.booking import Booking
from backend.models.platform import Platform
from backend.models.property import Property
from backend.models.room import Room
from backend.models.room_calendar import RoomCalendar
from backend.services.ical_sync_service import IcalSyncService


def migrated_database(tmp_path, monkeypatch, name="safeguards.db"):
    path = Path(tmp_path) / name
    monkeypatch.setattr(
        database_session, "DATABASE_URL", f"sqlite:///{path.as_posix()}"
    )
    command.upgrade(Config("alembic.ini"), "head")
    return path


def sqlite_connection(path, **kwargs):
    connection = sqlite3.connect(path, **kwargs)
    register_sqlite_functions(connection)
    return connection


def seed_rooms(connection):
    connection.execute(
        "INSERT INTO properties "
        "(id,name,address,city,owner,active) VALUES (1,'Piso','Calle','Elche','HSI',1)"
    )
    room_columns = {
        row[1] for row in connection.execute("PRAGMA table_info('rooms')")
    }
    if "master_calendar_token" in room_columns:
        connection.execute(
            "INSERT INTO rooms "
            "(id,property_id,code,display_order,base_price,active,master_calendar_token) "
            "VALUES (1,1,'H01',1,350,1,'token-room-1'),"
            "(2,1,'H02',2,350,1,'token-room-2')"
        )
    else:
        connection.execute(
            "INSERT INTO rooms "
            "(id,property_id,code,display_order,base_price,active) "
            "VALUES (1,1,'H01',1,350,1),(2,1,'H02',2,350,1)"
        )
    connection.commit()


def insert_booking(connection, booking_id, room_id, check_in, check_out):
    booking_columns = {
        row[1] for row in connection.execute("PRAGMA table_info('bookings')")
    }
    if "ical_uid" in booking_columns:
        connection.execute(
            "INSERT INTO bookings "
            "(id,room_id,origin,check_in,check_out,ical_uid) VALUES (?,?,?,?,?,?)",
            (booking_id, room_id, "manual", check_in, check_out, f"ical-{booking_id}"),
        )
    else:
        connection.execute(
            "INSERT INTO bookings "
            "(id,room_id,origin,check_in,check_out) VALUES (?,?,?,?,?)",
            (booking_id, room_id, "manual", check_in, check_out),
        )


@pytest.mark.alembic_audit
def test_overlap_triggers_cover_insert_update_contiguous_and_other_rooms(
    tmp_path, monkeypatch
):
    path = migrated_database(tmp_path, monkeypatch)
    connection = sqlite_connection(path)
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        seed_rooms(connection)
        insert_booking(connection, 1, 1, "2026-09-10", "2026-09-20")
        connection.commit()

        with pytest.raises(sqlite3.IntegrityError, match="booking_overlap"):
            insert_booking(connection, 2, 1, "2026-09-15", "2026-09-25")
        connection.rollback()

        insert_booking(connection, 2, 1, "2026-09-20", "2026-09-25")
        insert_booking(connection, 3, 2, "2026-09-10", "2026-09-20")
        connection.commit()

        with pytest.raises(sqlite3.IntegrityError, match="booking_overlap"):
            connection.execute(
                "UPDATE bookings SET check_in='2026-09-15' WHERE id=2"
            )
        connection.rollback()
        assert connection.execute("SELECT COUNT(*) FROM bookings").fetchone()[0] == 3
    finally:
        connection.close()


@pytest.mark.alembic_audit
def test_concurrent_conflicting_writes_allow_at_most_one_commit(
    tmp_path, monkeypatch
):
    path = migrated_database(tmp_path, monkeypatch, "concurrent.db")
    setup = sqlite_connection(path)
    seed_rooms(setup)
    setup.close()
    barrier = threading.Barrier(2)
    results = []

    def writer(booking_id, check_in, check_out):
        connection = sqlite_connection(path, timeout=5)
        connection.execute("PRAGMA busy_timeout=5000")
        try:
            barrier.wait()
            insert_booking(connection, booking_id, 1, check_in, check_out)
            connection.commit()
            results.append("committed")
        except (sqlite3.IntegrityError, sqlite3.OperationalError) as error:
            connection.rollback()
            results.append(str(error))
        finally:
            connection.close()

    threads = [
        threading.Thread(target=writer, args=(1, "2026-09-10", "2026-09-20")),
        threading.Thread(target=writer, args=(2, "2026-09-15", "2026-09-25")),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    check = sqlite_connection(path)
    try:
        persisted = check.execute("SELECT COUNT(*) FROM bookings").fetchone()[0]
    finally:
        check.close()
    assert persisted == results.count("committed") == 1
    assert len(results) == 2


@pytest.mark.alembic_audit
def test_trigger_allows_historical_reconstruction_but_protects_new(
    tmp_path, monkeypatch
):
    path = migrated_database(tmp_path, monkeypatch, "historical_rule.db")
    connection = sqlite_connection(path)
    try:
        connection.create_function(
            "rentalmanager_business_date", 0, lambda: "2026-08-17"
        )
        seed_rooms(connection)
        insert_booking(connection, 1, 1, "2026-05-08", "2026-08-31")
        insert_booking(connection, 2, 1, "2026-04-13", "2026-05-31")
        connection.commit()

        with pytest.raises(sqlite3.IntegrityError, match="booking_overlap"):
            connection.execute(
                "UPDATE bookings SET check_out='2026-09-01' WHERE id=2"
            )
        connection.rollback()
        assert connection.execute(
            "SELECT check_out FROM bookings WHERE id=2"
        ).fetchone()[0] == "2026-05-31"
    finally:
        connection.close()


@pytest.mark.alembic_audit
def test_trigger_uses_intersection_end_for_insert_and_update(
    tmp_path, monkeypatch
):
    path = migrated_database(tmp_path, monkeypatch, "intersection_rule.db")
    connection = sqlite_connection(path)
    try:
        connection.create_function(
            "rentalmanager_business_date", 0, lambda: "2026-08-17"
        )
        seed_rooms(connection)
        connection.execute(
            "INSERT INTO rooms "
            "(id,property_id,code,display_order,base_price,active,master_calendar_token) "
            "VALUES (3,1,'H03',3,350,1,'token-room-3')"
        )
        insert_booking(connection, 1, 1, "2026-04-13", "2026-05-31")

        # The candidate continues into the future, but the shared interval
        # ended in May and is therefore historical.
        insert_booking(connection, 2, 1, "2026-05-08", "2026-08-31")
        insert_booking(connection, 3, 2, "2026-04-13", "2026-05-31")
        insert_booking(connection, 4, 2, "2026-09-01", "2026-10-01")
        connection.commit()

        connection.execute(
            "UPDATE bookings SET check_in='2026-05-10', "
            "check_out='2026-08-30' WHERE id=4"
        )
        connection.commit()

        insert_booking(connection, 5, 3, "2026-08-01", "2026-08-17")
        insert_booking(connection, 6, 3, "2026-08-10", "2026-09-01")
        connection.commit()

        with pytest.raises(sqlite3.IntegrityError, match="booking_overlap"):
            insert_booking(connection, 7, 3, "2026-08-16", "2026-08-20")
        connection.rollback()

        with pytest.raises(sqlite3.IntegrityError, match="booking_overlap"):
            connection.execute(
                "UPDATE bookings SET room_id=3, check_in='2026-08-16', "
                "check_out='2026-08-20' WHERE id=1"
            )
        connection.rollback()
    finally:
        connection.close()


@pytest.mark.alembic_audit
def test_booking_write_without_business_date_function_fails_closed(
    tmp_path, monkeypatch
):
    path = migrated_database(tmp_path, monkeypatch, "missing_function.db")
    setup = sqlite_connection(path)
    seed_rooms(setup)
    setup.close()

    connection = sqlite3.connect(path)
    try:
        with pytest.raises(
            sqlite3.OperationalError,
            match="rentalmanager_business_date",
        ):
            insert_booking(
                connection, 1, 1, "2026-09-10", "2026-09-20"
            )
        connection.rollback()
    finally:
        connection.close()


@pytest.mark.alembic_audit
def test_downgrade_refuses_existing_historical_overlaps(
    tmp_path, monkeypatch
):
    path = migrated_database(tmp_path, monkeypatch, "downgrade_history.db")
    connection = sqlite_connection(path)
    try:
        seed_rooms(connection)
        insert_booking(connection, 1, 1, "2026-04-01", "2026-04-30")
        insert_booking(connection, 2, 1, "2026-04-13", "2026-05-31")
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(RuntimeError, match="historical overlaps"):
        command.downgrade(Config("alembic.ini"), "e5a7c9d1b304")

    check = sqlite_connection(path)
    try:
        assert check.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()[0] == "f8b2d4e6a405"
        assert check.execute("SELECT count(*) FROM bookings").fetchone()[0] == 2
    finally:
        check.close()


@pytest.mark.alembic_audit
def test_safeguard_migration_stops_on_historical_overlap(tmp_path, monkeypatch):
    path = Path(tmp_path) / "unsafe_history.db"
    monkeypatch.setattr(
        database_session, "DATABASE_URL", f"sqlite:///{path.as_posix()}"
    )
    config = Config("alembic.ini")
    command.upgrade(config, "4a3e7bc2d901")
    connection = sqlite_connection(path)
    seed_rooms(connection)
    insert_booking(connection, 1, 1, "2026-09-10", "2026-09-20")
    insert_booking(connection, 2, 1, "2026-09-15", "2026-09-25")
    connection.commit()
    connection.close()

    with pytest.raises(RuntimeError, match="historical overlaps"):
        command.upgrade(config, "head")


@pytest.mark.alembic_audit
def test_ical_multi_update_swap_is_rejected_atomically_by_real_trigger(
    tmp_path, monkeypatch
):
    path = migrated_database(tmp_path, monkeypatch, "ical_swap.db")
    engine = create_engine(f"sqlite:///{path.as_posix()}")
    session = sessionmaker(bind=engine, autoflush=False)()
    property_obj = Property(
        name="Piso", address="Calle", city="Elche", owner="HSI", active=True
    )
    session.add(property_obj)
    session.flush()
    room = Room(
        property_id=property_obj.id, code="H01", display_order=1,
        base_price=350, active=True,
    )
    platform = Platform(
        name="Platform", slug="platform", active=True,
        supports_import=True, supports_export=False,
    )
    session.add_all([room, platform])
    session.flush()
    calendar = RoomCalendar(
        room_id=room.id, platform_id=platform.id,
        import_url="https://calendar.example/feed.ics", active=True,
    )
    session.add(calendar)
    session.flush()
    first = Booking(
        room_id=room.id, room_calendar_id=calendar.id, origin="platform",
        external_reference="FIRST", check_in=date(2026, 9, 1), check_out=date(2026, 9, 3),
    )
    second = Booking(
        room_id=room.id, room_calendar_id=calendar.id, origin="platform",
        external_reference="SECOND", check_in=date(2026, 9, 3), check_out=date(2026, 9, 5),
    )
    session.add_all([first, second])
    session.commit()

    class HttpClient:
        def download(self, _url):
            return b"ical"

    class Parser:
        def parse(self, _content):
            return [
                NormalizedIcalEvent(
                    "FIRST", date(2026, 9, 3), date(2026, 9, 5), None, False
                ),
                NormalizedIcalEvent(
                    "SECOND", date(2026, 9, 1), date(2026, 9, 3), None, False
                ),
            ]

    result = IcalSyncService(HttpClient(), Parser()).synchronize(
        session, calendar.id
    )

    assert result.message == "room_calendar_sync_overlap"
    session.refresh(first)
    session.refresh(second)
    assert first.check_in == date(2026, 9, 1)
    assert second.check_in == date(2026, 9, 3)
    assert calendar.last_sync_at is None
    session.close()
    engine.dispose()
