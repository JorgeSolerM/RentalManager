import hashlib
import shutil
import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.schema import UniqueConstraint

from backend.database.base import Base
import backend.database.session as database_session
import backend.models  # noqa: F401


REPAIR_REVISION = "4a3e7bc2d901"
SAFEGUARDS_REVISION = "c7d9e4a1b602"
ROOM_CALENDAR_EXPORT_REVISION = "d4e8f1a2c703"
MASTER_CALENDAR_REVISION = "a6f3b9c8d210"
AUTOMATIC_SYNC_REVISION = "e5a7c9d1b304"
HISTORICAL_OVERLAP_REVISION = "f8b2d4e6a405"


def configure_temporary_database(monkeypatch, database_path: Path) -> tuple[Config, str]:
    database_url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setattr(database_session, "DATABASE_URL", database_url)
    return Config("alembic.ini"), database_url


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def table_counts(database_path: Path) -> dict[str, int]:
    connection = sqlite3.connect(f"file:{database_path.as_posix()}?mode=ro", uri=True)
    try:
        return {
            table_name: connection.execute(
                f'SELECT COUNT(*) FROM "{table_name}"'
            ).fetchone()[0]
            for table_name in Base.metadata.tables
        }
    finally:
        connection.close()


def schema_snapshot(database_path: Path, table_names: tuple[str, ...]) -> dict[str, int]:
    connection = sqlite3.connect(f"file:{database_path.as_posix()}?mode=ro", uri=True)
    try:
        return {
            name: connection.execute(
                "SELECT rootpage FROM sqlite_master WHERE type = 'table' AND name = ?",
                (name,),
            ).fetchone()[0]
            for name in table_names
        }
    finally:
        connection.close()


def assert_schema_matches_models(database_url: str) -> None:
    engine = create_engine(database_url)
    try:
        inspector = inspect(engine)
        assert set(inspector.get_table_names()) >= set(Base.metadata.tables)

        for table_name, model_table in Base.metadata.tables.items():
            actual_columns = {
                column["name"]: column
                for column in inspector.get_columns(table_name)
            }
            assert set(actual_columns) == set(model_table.columns.keys())
            for model_column in model_table.columns:
                actual_column = actual_columns[model_column.name]
                assert str(actual_column["type"]) == str(model_column.type)
                assert actual_column["nullable"] is model_column.nullable

            expected_indexes = {index.name for index in model_table.indexes}
            actual_indexes = {
                index["name"] for index in inspector.get_indexes(table_name)
            }
            assert expected_indexes <= actual_indexes

            expected_foreign_keys = {
                (
                    tuple(constraint.column_keys),
                    constraint.elements[0].column.table.name,
                    tuple(element.column.name for element in constraint.elements),
                )
                for constraint in model_table.foreign_key_constraints
            }
            actual_foreign_keys = {
                (
                    tuple(constraint["constrained_columns"]),
                    constraint["referred_table"],
                    tuple(constraint["referred_columns"]),
                )
                for constraint in inspector.get_foreign_keys(table_name)
            }
            assert expected_foreign_keys == actual_foreign_keys

            expected_unique_constraints = {
                tuple(constraint.columns.keys())
                for constraint in model_table.constraints
                if isinstance(constraint, UniqueConstraint)
            }
            actual_unique_constraints = {
                tuple(constraint["column_names"])
                for constraint in inspector.get_unique_constraints(table_name)
            }
            assert expected_unique_constraints == actual_unique_constraints
    finally:
        engine.dispose()


@pytest.mark.alembic_audit
def test_alembic_upgrade_head_builds_complete_schema_in_temporary_sqlite(
    tmp_path, monkeypatch
):
    database_path = Path(tmp_path) / "alembic_empty.db"
    config, database_url = configure_temporary_database(monkeypatch, database_path)
    foreign_key_settings = []

    def observe_alembic_connection(dbapi_connection, _connection_record):
        if isinstance(dbapi_connection, sqlite3.Connection):
            foreign_key_settings.append(
                dbapi_connection.execute("PRAGMA foreign_keys").fetchone()[0]
            )

    event.listen(Engine, "connect", observe_alembic_connection)
    try:
        command.upgrade(config, "head")
    finally:
        event.remove(Engine, "connect", observe_alembic_connection)

    assert foreign_key_settings == [1]
    assert_schema_matches_models(database_url)
    connection = sqlite3.connect(f"file:{database_path.as_posix()}?mode=ro", uri=True)
    try:
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            HISTORICAL_OVERLAP_REVISION,
        )
    finally:
        connection.close()


@pytest.mark.alembic_audit
def test_alembic_upgrade_head_accepts_current_database_copy(
    tmp_path, monkeypatch
):
    source_path = Path(database_session.DATABASE_PATH)
    source_hash_before = file_hash(source_path)
    database_path = Path(tmp_path) / "historical_copy.db"
    shutil.copy2(source_path, database_path)
    counts_before = table_counts(database_path)
    roots_before = schema_snapshot(database_path, ("properties",))
    copy_hash_before = file_hash(database_path)
    config, database_url = configure_temporary_database(monkeypatch, database_path)

    connection = sqlite3.connect(f"file:{database_path.as_posix()}?mode=ro", uri=True)
    try:
        source_revision = connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()[0]
        assert source_revision in {
            SAFEGUARDS_REVISION,
            ROOM_CALENDAR_EXPORT_REVISION,
            MASTER_CALENDAR_REVISION,
            AUTOMATIC_SYNC_REVISION,
            HISTORICAL_OVERLAP_REVISION,
        }
    finally:
        connection.close()

    command.upgrade(config, "head")
    command.current(config)

    assert table_counts(database_path) == counts_before
    assert schema_snapshot(database_path, ("properties",)) == roots_before
    if source_revision == HISTORICAL_OVERLAP_REVISION:
        assert file_hash(database_path) == copy_hash_before
    assert_schema_matches_models(database_url)
    connection = sqlite3.connect(f"file:{database_path.as_posix()}?mode=ro", uri=True)
    try:
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            HISTORICAL_OVERLAP_REVISION,
        )
    finally:
        connection.close()
    assert file_hash(source_path) == source_hash_before


@pytest.mark.alembic_audit
def test_booking_safeguards_upgrade_and_downgrade_on_temporary_sqlite(
    tmp_path, monkeypatch
):
    database_path = Path(tmp_path) / "safeguards_round_trip.db"
    config, _database_url = configure_temporary_database(monkeypatch, database_path)
    command.upgrade(config, "head")

    connection = sqlite3.connect(database_path)
    try:
        index_names = {
            row[1] for row in connection.execute("PRAGMA index_list('bookings')")
        }
        trigger_names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'trigger'"
            )
        }
        assert "uq_bookings_calendar_external_reference" in index_names
        assert trigger_names >= {
            "trg_bookings_no_overlap_insert",
            "trg_bookings_no_overlap_update",
        }
    finally:
        connection.close()

    command.downgrade(config, REPAIR_REVISION)
    connection = sqlite3.connect(database_path)
    try:
        assert "uq_bookings_calendar_external_reference" not in {
            row[1] for row in connection.execute("PRAGMA index_list('bookings')")
        }
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'trigger'"
        ).fetchall() == []
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            REPAIR_REVISION,
        )
    finally:
        connection.close()

    command.upgrade(config, "head")
    connection = sqlite3.connect(f"file:{database_path.as_posix()}?mode=ro", uri=True)
    try:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            HISTORICAL_OVERLAP_REVISION,
    )
    finally:
        connection.close()


@pytest.mark.alembic_audit
def test_room_calendar_export_column_upgrade_downgrade_upgrade(
    tmp_path, monkeypatch
):
    database_path = Path(tmp_path) / "room_calendar_export_round_trip.db"
    config, database_url = configure_temporary_database(monkeypatch, database_path)
    command.upgrade(config, "head")

    inspector = inspect(create_engine(database_url))
    assert "export_url" not in {
        column["name"] for column in inspector.get_columns("room_calendars")
    }

    command.downgrade(config, SAFEGUARDS_REVISION)
    connection = sqlite3.connect(database_path)
    try:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(room_calendars)")
        }
        assert "export_url" in columns
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            SAFEGUARDS_REVISION,
        )
    finally:
        connection.close()

    command.upgrade(config, "head")
    connection = sqlite3.connect(f"file:{database_path.as_posix()}?mode=ro", uri=True)
    try:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(room_calendars)")
        }
        assert "export_url" not in columns
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            HISTORICAL_OVERLAP_REVISION,
        )
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()


@pytest.mark.alembic_audit
def test_master_calendar_identity_backfill_and_round_trip(tmp_path, monkeypatch):
    database_path = Path(tmp_path) / "master_calendar_round_trip.db"
    config, _database_url = configure_temporary_database(monkeypatch, database_path)
    command.upgrade(config, ROOM_CALENDAR_EXPORT_REVISION)

    connection = sqlite3.connect(database_path)
    try:
        connection.execute(
            "INSERT INTO properties "
            "(id,name,address,city,owner,active) "
            "VALUES (1,'Piso','Calle','Elche','HSI',1)"
        )
        connection.execute(
            "INSERT INTO rooms "
            "(id,property_id,code,display_order,base_price,active) "
            "VALUES (1,1,'H01',1,350,1),(2,1,'H02',2,350,1)"
        )
        connection.execute(
            "INSERT INTO bookings "
            "(id,room_id,origin,check_in,check_out) VALUES "
            "(1,1,'manual','2026-09-01','2026-09-05'),"
            "(2,1,'manual','2026-09-05','2026-09-10')"
        )
        connection.commit()
    finally:
        connection.close()


    command.upgrade(config, "head")
    connection = sqlite3.connect(database_path)
    try:
        room_tokens = connection.execute(
            "SELECT master_calendar_token FROM rooms"
        ).fetchall()
        booking_uids = connection.execute(
            "SELECT ical_uid FROM bookings"
        ).fetchall()
        assert len({row[0] for row in room_tokens}) == 2
        assert all(row[0] for row in room_tokens)
        assert len({row[0] for row in booking_uids}) == 2
        assert all(row[0] for row in booking_uids)
        assert {
            row[1] for row in connection.execute("PRAGMA index_list('bookings')")
        } >= {
            "uq_bookings_ical_uid",
            "uq_bookings_calendar_external_reference",
        }
        assert {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger'"
            )
        } >= {
            "trg_bookings_no_overlap_insert",
            "trg_bookings_no_overlap_update",
        }
    finally:
        connection.close()

    command.downgrade(config, ROOM_CALENDAR_EXPORT_REVISION)
    connection = sqlite3.connect(database_path)
    try:
        assert "master_calendar_token" not in {
            row[1] for row in connection.execute("PRAGMA table_info('rooms')")
        }
        assert "ical_uid" not in {
            row[1] for row in connection.execute("PRAGMA table_info('bookings')")
        }
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger'"
            )
        } >= {
            "trg_bookings_no_overlap_insert",
            "trg_bookings_no_overlap_update",
        }
    finally:
        connection.close()

    command.upgrade(config, "head")
    connection = sqlite3.connect(f"file:{database_path.as_posix()}?mode=ro", uri=True)
    try:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            HISTORICAL_OVERLAP_REVISION,
        )
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute("SELECT COUNT(*) FROM rooms").fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM bookings").fetchone()[0] == 2
    finally:
        connection.close()


@pytest.mark.alembic_audit
def test_automatic_sync_state_upgrade_downgrade_upgrade(tmp_path, monkeypatch):
    database_path = Path(tmp_path) / "automatic_sync_round_trip.db"
    config, _database_url = configure_temporary_database(monkeypatch, database_path)
    command.upgrade(config, MASTER_CALENDAR_REVISION)
    connection = sqlite3.connect(database_path)
    try:
        connection.execute(
            "INSERT INTO properties (id,name,address,city,owner,active) "
            "VALUES (1,'Piso','Calle','Madrid','Owner',1)"
        )
        connection.execute(
            "INSERT INTO rooms "
            "(id,property_id,code,display_order,base_price,active,master_calendar_token) "
            "VALUES (1,1,'R1',1,500,1,'room-token')"
        )
        connection.execute(
            "INSERT INTO platforms "
            "(id,name,slug,supports_import,supports_export,active) "
            "VALUES (1,'Platform','platform',1,1,1)"
        )
        connection.execute(
            "INSERT INTO room_calendars "
            "(id,room_id,platform_id,import_url,active) "
            "VALUES (1,1,1,'https://example.com/feed.ics',1)"
        )
        connection.execute(
            "INSERT INTO bookings "
            "(id,room_id,room_calendar_id,origin,external_reference,check_in,check_out,ical_uid) "
            "VALUES (1,1,1,'platform','EXT','2026-09-01','2026-09-05','ical-uid')"
        )
        connection.commit()
    finally:
        connection.close()

    command.upgrade(config, "head")
    connection = sqlite3.connect(database_path)
    try:
        row = connection.execute(
            "SELECT last_sync_attempt_at,last_sync_status,last_sync_error,"
            "consecutive_failures,automatic_sync_enabled FROM room_calendars"
        ).fetchone()
        assert row == (None, None, None, 0, 1)
    finally:
        connection.close()

    command.downgrade(config, MASTER_CALENDAR_REVISION)
    connection = sqlite3.connect(database_path)
    try:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(room_calendars)")
        }
        assert "automatic_sync_enabled" not in columns
        assert "last_sync_attempt_at" not in columns
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute("SELECT COUNT(*) FROM bookings").fetchone()[0] == 1
    finally:
        connection.close()

    command.upgrade(config, "head")
    connection = sqlite3.connect(f"file:{database_path.as_posix()}?mode=ro", uri=True)
    try:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            HISTORICAL_OVERLAP_REVISION,
        )
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute(
            "SELECT consecutive_failures,automatic_sync_enabled FROM room_calendars"
        ).fetchone() == (0, 1)
    finally:
        connection.close()
