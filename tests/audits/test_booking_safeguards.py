import sqlite3
import threading
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

import backend.database.session as database_session


def migrated_database(tmp_path, monkeypatch, name="safeguards.db"):
    path = Path(tmp_path) / name
    monkeypatch.setattr(
        database_session, "DATABASE_URL", f"sqlite:///{path.as_posix()}"
    )
    command.upgrade(Config("alembic.ini"), "head")
    return path


def seed_rooms(connection):
    connection.execute(
        "INSERT INTO properties "
        "(id,name,address,city,owner,active) VALUES (1,'Piso','Calle','Elche','HSI',1)"
    )
    connection.execute(
        "INSERT INTO rooms "
        "(id,property_id,code,display_order,base_price,active) "
        "VALUES (1,1,'H01',1,350,1),(2,1,'H02',2,350,1)"
    )
    connection.commit()


def insert_booking(connection, booking_id, room_id, check_in, check_out):
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
    connection = sqlite3.connect(path)
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
    setup = sqlite3.connect(path)
    seed_rooms(setup)
    setup.close()
    barrier = threading.Barrier(2)
    results = []

    def writer(booking_id, check_in, check_out):
        connection = sqlite3.connect(path, timeout=5)
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

    check = sqlite3.connect(path)
    try:
        persisted = check.execute("SELECT COUNT(*) FROM bookings").fetchone()[0]
    finally:
        check.close()
    assert persisted == results.count("committed") == 1
    assert len(results) == 2


@pytest.mark.alembic_audit
def test_safeguard_migration_stops_on_historical_overlap(tmp_path, monkeypatch):
    path = Path(tmp_path) / "unsafe_history.db"
    monkeypatch.setattr(
        database_session, "DATABASE_URL", f"sqlite:///{path.as_posix()}"
    )
    config = Config("alembic.ini")
    command.upgrade(config, "4a3e7bc2d901")
    connection = sqlite3.connect(path)
    seed_rooms(connection)
    insert_booking(connection, 1, 1, "2026-09-10", "2026-09-20")
    insert_booking(connection, 2, 1, "2026-09-15", "2026-09-25")
    connection.commit()
    connection.close()

    with pytest.raises(RuntimeError, match="historical overlaps"):
        command.upgrade(config, "head")
