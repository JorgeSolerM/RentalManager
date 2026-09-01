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
MASTER_CALENDAR_OBSERVATION_REVISION = "c9e1f3a5b607"
IMPORTED_PRESENCE_REVISION = "d2f4a6b8c901"
OPERATIONAL_OVERLAP_REVISION = "e3a5c7d9f102"
PUBLICATION_FOUNDATION_REVISION = "f6b8d0e2a413"
OPTIONAL_ROOM_PRICE_REVISION = "a8c1e4f6b209"
SHARED_BATHROOM_REVISION = "c6e8a0b2d437"
FINANCIAL_LEDGER_REVISION = "f2d4b6c8a014"
PERSON_BOOKING_PARTY_REVISION = "a3c5e7f9b126"
HEAD_REVISION = "b4d6f8a0c237"


@pytest.mark.alembic_audit
def test_person_iban_upgrade_downgrade_reupgrade_without_backfill(tmp_path, monkeypatch):
    database_path = Path(tmp_path) / "person_iban_round_trip.db"
    config, _ = configure_temporary_database(monkeypatch, database_path)
    command.upgrade(config, PERSON_BOOKING_PARTY_REVISION)
    connection = sqlite3.connect(database_path)
    connection.execute(
        "INSERT INTO persons (id,full_name,active,verification_status,source) "
        "VALUES (1,'Persona existente',1,'unverified','manual')"
    )
    connection.commit()
    connection.close()

    command.upgrade(config, HEAD_REVISION)
    connection = sqlite3.connect(database_path)
    try:
        assert "iban" in {
            row[1] for row in connection.execute("PRAGMA table_info(persons)")
        }
        assert connection.execute("SELECT iban FROM persons WHERE id=1").fetchone() == (None,)
        assert connection.execute("PRAGMA quick_check").fetchone() == ("ok",)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()

    command.downgrade(config, PERSON_BOOKING_PARTY_REVISION)
    connection = sqlite3.connect(database_path)
    try:
        assert "iban" not in {
            row[1] for row in connection.execute("PRAGMA table_info(persons)")
        }
        assert connection.execute("SELECT full_name FROM persons WHERE id=1").fetchone() == ("Persona existente",)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()

    command.upgrade(config, HEAD_REVISION)


@pytest.mark.alembic_audit
def test_person_booking_party_migration_is_conservative_and_reversible(tmp_path, monkeypatch):
    database_path = Path(tmp_path) / "person_booking_party.db"
    config, _ = configure_temporary_database(monkeypatch, database_path)
    command.upgrade(config, "f2d4b6c8a014")
    connection = sqlite3.connect(database_path)
    connection.create_function("rentalmanager_business_date", 0, lambda: "2026-09-01")
    connection.execute("INSERT INTO properties (id,name,address,city,owner,active) VALUES (1,'P','A','C','O',1)")
    connection.execute("INSERT INTO rooms (id,property_id,code,display_order,active,master_calendar_token,operational_since) VALUES (1,1,'R',1,1,'token','2026-09-01')")
    connection.executemany("INSERT INTO guests (id,full_name,display_name,active) VALUES (?,?,?,1)", [(1,"Nombre A y Nombre B","Nombre A y Nombre B"),(2,"Mismo","Mismo"),(3,"Mismo","Mismo")])
    connection.execute("INSERT INTO bookings (id,room_id,guest_id,origin,check_in,check_out,ical_uid) VALUES (1,1,1,'manual','2026-09-01','2026-10-01','uid')")
    connection.commit(); connection.close()
    command.upgrade(config, HEAD_REVISION)
    connection = sqlite3.connect(database_path)
    try:
        assert connection.execute("SELECT COUNT(*) FROM persons").fetchone() == (3,)
        assert connection.execute("SELECT full_name FROM persons WHERE id=1").fetchone() == ("Nombre A y Nombre B",)
        assert connection.execute("SELECT COUNT(*) FROM persons WHERE full_name='Mismo'").fetchone() == (2,)
        assert connection.execute("SELECT booking_id,person_id,role FROM booking_parties").fetchone() == (1,1,"unclassified")
        assert connection.execute("SELECT guest_id,source_guest_name FROM bookings").fetchone() == (1,"Nombre A y Nombre B")
        for table in ("booking_financial_terms","booking_charges","payments","payment_allocations"):
            assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone() == (0,)
            assert all(
                foreign_key[2] not in {"persons", "booking_parties"}
                for foreign_key in connection.execute(
                    f"PRAGMA foreign_key_list({table})"
                )
            )
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally: connection.close()
    command.downgrade(config, "f2d4b6c8a014")
    connection = sqlite3.connect(database_path)
    try:
        assert "source_guest_name" not in {row[1] for row in connection.execute("PRAGMA table_info(bookings)")}
        assert connection.execute("SELECT guest_id FROM bookings").fetchone() == (1,)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally: connection.close()
    command.upgrade(config, HEAD_REVISION)


@pytest.mark.alembic_audit
def test_financial_ledger_upgrade_downgrade_upgrade_without_backfill(tmp_path, monkeypatch):
    database_path = Path(tmp_path) / "financial_ledger_round_trip.db"
    config, _ = configure_temporary_database(monkeypatch, database_path)
    command.upgrade(config, "e1c3a5b7d902")
    connection = sqlite3.connect(database_path)
    connection.create_function("rentalmanager_business_date", 0, lambda: "2026-09-01")
    connection.execute(
        "INSERT INTO properties (id,name,address,city,owner,active) "
        "VALUES (1,'Piso','Calle','Elche','Owner',1)"
    )
    connection.execute(
        "INSERT INTO rooms (id,property_id,code,display_order,active,master_calendar_token,operational_since) "
        "VALUES (1,1,'R1',1,1,'token','2026-09-01')"
    )
    connection.execute(
        "INSERT INTO bookings (id,room_id,origin,check_in,check_out,price,ical_uid) "
        "VALUES (1,1,'manual','2026-09-01','2027-06-30',445,'financial-test')"
    )
    connection.commit(); connection.close()

    command.upgrade(config, HEAD_REVISION)
    connection = sqlite3.connect(database_path)
    try:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (HEAD_REVISION,)
        for table in ("booking_financial_terms", "booking_charges", "payments", "payment_allocations"):
            assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
        assert connection.execute("SELECT price FROM bookings WHERE id=1").fetchone() == (445,)
        assert connection.execute("PRAGMA quick_check").fetchone() == ("ok",)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()

    command.downgrade(config, "e1c3a5b7d902")
    connection = sqlite3.connect(database_path)
    try:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "booking_charges" not in tables
        assert connection.execute("SELECT price FROM bookings WHERE id=1").fetchone() == (445,)
    finally:
        connection.close()
    command.upgrade(config, HEAD_REVISION)


@pytest.mark.alembic_audit
def test_room_operational_since_upgrade_downgrade_upgrade(tmp_path, monkeypatch):
    database_path = Path(tmp_path) / "room_operational_since.db"
    config, _ = configure_temporary_database(monkeypatch, database_path)
    command.upgrade(config, "d7f9b1c3e548")
    connection = sqlite3.connect(database_path)
    connection.execute(
        "INSERT INTO properties "
        "(id,name,address,city,owner,active,is_published) "
        "VALUES (1,'P','A','C','O',1,0)"
    )
    connection.execute(
        "INSERT INTO rooms "
        "(id,property_id,code,display_order,active,is_published,master_calendar_token) "
        "VALUES (1,1,'R1',1,1,0,'token-1')"
    )
    connection.commit()
    connection.close()

    command.upgrade(config, HEAD_REVISION)
    connection = sqlite3.connect(database_path)
    try:
        assert connection.execute(
            "SELECT operational_since FROM rooms WHERE id=1"
        ).fetchone() == ("2026-08-26",)
        assert connection.execute("PRAGMA quick_check").fetchone() == ("ok",)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()

    command.downgrade(config, "d7f9b1c3e548")
    connection = sqlite3.connect(database_path)
    try:
        assert "operational_since" not in {
            row[1] for row in connection.execute("PRAGMA table_info(rooms)")
        }
    finally:
        connection.close()

    command.upgrade(config, HEAD_REVISION)
    connection = sqlite3.connect(database_path)
    try:
        assert connection.execute(
            "SELECT operational_since FROM rooms WHERE id=1"
        ).fetchone() == ("2026-08-26",)
        assert connection.execute("PRAGMA quick_check").fetchone() == ("ok",)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()


@pytest.mark.alembic_audit
def test_booking_operational_dates_upgrade_downgrade_upgrade(
    tmp_path, monkeypatch
):
    database_path = Path(tmp_path) / "booking_operational_dates.db"
    config, _ = configure_temporary_database(monkeypatch, database_path)
    command.upgrade(config, SHARED_BATHROOM_REVISION)

    connection = sqlite3.connect(database_path)
    try:
        before = {
            row[1] for row in connection.execute("PRAGMA table_info(bookings)")
        }
        assert "expected_arrival_date" not in before
        assert "expected_departure_date" not in before
    finally:
        connection.close()

    command.upgrade(config, HEAD_REVISION)
    connection = sqlite3.connect(database_path)
    try:
        upgraded = {
            row[1]: row for row in connection.execute("PRAGMA table_info(bookings)")
        }
        assert upgraded["expected_arrival_date"][3] == 0
        assert upgraded["expected_departure_date"][3] == 0
    finally:
        connection.close()

    command.downgrade(config, SHARED_BATHROOM_REVISION)
    command.upgrade(config, HEAD_REVISION)
    connection = sqlite3.connect(database_path)
    try:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(bookings)")
        }
        assert {"expected_arrival_date", "expected_departure_date"} <= columns
        assert connection.execute("PRAGMA quick_check").fetchone() == ("ok",)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()


@pytest.mark.alembic_audit
def test_property_rules_requirements_upgrade_downgrade_upgrade(tmp_path, monkeypatch):
    database_path = Path(tmp_path) / "property_rules_requirements.db"
    config, _ = configure_temporary_database(monkeypatch, database_path)
    command.upgrade(config, "f9b1d3e5a640")
    connection = sqlite3.connect(database_path)
    connection.execute(
        "INSERT INTO properties "
        "(id,name,address,city,owner,active,is_published) "
        "VALUES (1,'P','A','C','O',1,0)"
    )
    connection.commit()
    connection.close()

    command.upgrade(config, HEAD_REVISION)
    connection = sqlite3.connect(database_path)
    try:
        values = connection.execute(
            "SELECT smoking_allowed,pets_allowed,"
            "musical_instruments_allowed,minimum_tenant_age,maximum_tenant_age "
            "FROM properties WHERE id=1"
        ).fetchone()
        assert values == (None, None, None, None, None)
        assert "couples_allowed" not in {
            row[1] for row in connection.execute("PRAGMA table_info(properties)")
        }
        assert connection.execute(
            "SELECT shared_full_bathroom_count,shared_toilet_count "
            "FROM properties WHERE id=1"
        ).fetchone() == (None, None)
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE properties SET shared_toilet_count=-1 WHERE id=1"
            )
        connection.rollback()
        assert connection.execute(
            "SELECT COUNT(*) FROM rental_requirements"
        ).fetchone() == (5,)
        assert connection.execute(
            "SELECT COUNT(*) FROM property_requirements"
        ).fetchone() == (0,)
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE properties SET minimum_tenant_age=50, "
                "maximum_tenant_age=40 WHERE id=1"
            )
        connection.rollback()
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()

    command.downgrade(config, "f9b1d3e5a640")
    command.upgrade(config, HEAD_REVISION)
    connection = sqlite3.connect(database_path)
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM rental_requirements"
        ).fetchone() == (5,)
        assert connection.execute("PRAGMA quick_check").fetchone() == ("ok",)
    finally:
        connection.close()


@pytest.mark.alembic_audit
def test_manager_phone_upgrade_downgrade_upgrade(tmp_path, monkeypatch):
    database_path = Path(tmp_path) / "manager_phone.db"
    config, _ = configure_temporary_database(monkeypatch, database_path)
    command.upgrade(config, "c4e6a8b0d214")
    command.upgrade(config, "head")
    connection = sqlite3.connect(database_path)
    try:
        columns = {row[1]: row for row in connection.execute("PRAGMA table_info(managers)")}
        assert "phone" in columns and columns["phone"][3] == 0
        connection.execute("INSERT INTO managers (name,phone,active) VALUES (?,?,1)", ("Gestor", "+34 600 123 123"))
        assert connection.execute("SELECT phone FROM managers").fetchone()[0] == "+34 600 123 123"
    finally:
        connection.close()
    command.downgrade(config, "c4e6a8b0d214")
    command.upgrade(config, "head")


@pytest.mark.alembic_audit
def test_room_stay_months_upgrade_downgrade_upgrade(tmp_path, monkeypatch):
    database_path = Path(tmp_path) / "room_stay_months.db"
    config, _ = configure_temporary_database(monkeypatch, database_path)
    command.upgrade(config, "b1d3f5a7c902")
    command.upgrade(config, "head")
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("INSERT INTO properties (id,name,address,city,owner,active,is_published) VALUES (1,'P','A','C','O',1,0)")
        base = "INSERT INTO rooms (id,property_id,code,display_order,active,master_calendar_token,is_published,minimum_stay_months,maximum_stay_months) VALUES (?,?,?,?,?,?,0,?,?)"
        connection.execute(base, (1, 1, "R1", 1, 1, "t1", 0, None))
        connection.execute(base, (2, 1, "R2", 2, 1, "t2", 0, 3))
        for values in ((3, 1, "R3", 3, 1, "t3", -1, None), (4, 1, "R4", 4, 1, "t4", 0, 0), (5, 1, "R5", 5, 1, "t5", 3, 2)):
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(base, values)
            connection.rollback()
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()
    command.downgrade(config, "b1d3f5a7c902")
    command.upgrade(config, "head")


@pytest.mark.alembic_audit
def test_managers_and_room_highlights_upgrade_downgrade_upgrade(tmp_path, monkeypatch):
    database_path = Path(tmp_path) / "managers_highlights.db"
    config, _ = configure_temporary_database(monkeypatch, database_path)
    command.upgrade(config, "a8c1e4f6b209")
    connection = sqlite3.connect(database_path)
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("INSERT INTO properties (id,name,address,city,owner,active,is_published) VALUES (1,'P','A','C','O',1,0)")
    connection.execute("INSERT INTO rooms (id,property_id,code,display_order,active,master_calendar_token,is_published) VALUES (1,1,'R1',1,1,'token',0)")
    connection.commit(); connection.close()
    command.upgrade(config, "head")
    connection = sqlite3.connect(database_path)
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        connection.execute("INSERT INTO managers (id,name,active) VALUES (1,'Gestor',1)")
        connection.execute("UPDATE properties SET manager_id=1 WHERE id=1")
        feature_id = connection.execute("SELECT id FROM features WHERE slug='suministros-incluidos'").fetchone()[0]
        connection.execute("INSERT INTO room_public_highlights (room_id,feature_id,position) VALUES (1,?,0)", (feature_id,))
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("INSERT INTO room_public_highlights (room_id,feature_id,position) VALUES (1,999,4)")
        connection.rollback()
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()
    command.downgrade(config, "a8c1e4f6b209")
    command.upgrade(config, "head")


def configure_temporary_database(monkeypatch, database_path: Path) -> tuple[Config, str]:
    database_url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setattr(database_session, "DATABASE_URL", database_url)
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("ALEMBIC_REQUIRE_TEMPORARY_DATABASE", "1")
    return Config("alembic.ini"), database_url


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def table_counts(
    database_path: Path,
    table_names: set[str] | None = None,
) -> dict[str, int]:
    connection = sqlite3.connect(f"file:{database_path.as_posix()}?mode=ro", uri=True)
    try:
        names = table_names or set(Base.metadata.tables)
        return {
            table_name: connection.execute(
                f'SELECT COUNT(*) FROM "{table_name}"'
            ).fetchone()[0]
            for table_name in names
        }
    finally:
        connection.close()

@pytest.mark.alembic_audit
def test_master_calendar_observations_upgrade_downgrade_upgrade(
    tmp_path, monkeypatch
):
    database_path = Path(tmp_path) / "master_calendar_observations.db"
    config, _database_url = configure_temporary_database(monkeypatch, database_path)
    command.upgrade(config, HISTORICAL_OVERLAP_REVISION)
    connection = sqlite3.connect(database_path)
    try:
        connection.execute(
            "INSERT INTO properties (id,name,address,city,owner,active) "
            "VALUES (1,'Piso','Calle','Madrid','Owner',1)"
        )
        connection.execute(
            "INSERT INTO rooms "
            "(id,property_id,code,display_order,base_price,active,master_calendar_token) "
            "VALUES (1,1,'R1',1,500,1,'token')"
        )
        connection.execute(
            "INSERT INTO platforms "
            "(id,name,slug,supports_import,supports_export,active) "
            "VALUES (1,'Platform','platform',1,1,1)"
        )
        connection.execute(
            "INSERT INTO room_calendars "
            "(id,room_id,platform_id,active,automatic_sync_enabled,consecutive_failures) "
            "VALUES (1,1,1,1,1,0)"
        )
        connection.commit()
    finally:
        connection.close()

    command.upgrade(config, "head")
    connection = sqlite3.connect(database_path)
    try:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(room_calendars)")
        }
        assert {
            "master_calendar_first_request_at",
            "last_master_calendar_request_at",
            "master_calendar_request_count",
        } <= columns
        assert connection.execute(
            "SELECT master_calendar_request_count FROM room_calendars"
        ).fetchone() == (0,)
    finally:
        connection.close()

    command.downgrade(config, HISTORICAL_OVERLAP_REVISION)
    connection = sqlite3.connect(database_path)
    try:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(room_calendars)")
        }
        assert "master_calendar_request_count" not in columns
        assert connection.execute("SELECT COUNT(*) FROM room_calendars").fetchone() == (1,)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()

    command.upgrade(config, "head")
    connection = sqlite3.connect(database_path)
    try:
        assert connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone() == (HEAD_REVISION,)
        assert connection.execute(
            "SELECT master_calendar_request_count FROM room_calendars"
        ).fetchone() == (0,)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()


@pytest.mark.alembic_audit
def test_imported_presence_tracking_upgrade_downgrade_upgrade(
    tmp_path, monkeypatch
):
    database_path = Path(tmp_path) / "imported_presence_tracking.db"
    config, _database_url = configure_temporary_database(monkeypatch, database_path)
    command.upgrade(config, MASTER_CALENDAR_OBSERVATION_REVISION)
    connection = sqlite3.connect(database_path)
    database_session.register_sqlite_functions(connection)
    try:
        connection.execute(
            "INSERT INTO properties (id,name,address,city,owner,active) "
            "VALUES (1,'Piso','Calle','Madrid','Owner',1)"
        )
        connection.execute(
            "INSERT INTO rooms "
            "(id,property_id,code,display_order,base_price,active,master_calendar_token) "
            "VALUES (1,1,'R1',1,500,1,'token')"
        )
        connection.execute(
            "INSERT INTO platforms "
            "(id,name,slug,supports_import,supports_export,active) "
            "VALUES (1,'HousingAnywhere','housinganywhere',1,1,1)"
        )
        connection.execute(
            "INSERT INTO room_calendars "
            "(id,room_id,platform_id,active,automatic_sync_enabled,consecutive_failures,master_calendar_request_count) "
            "VALUES (1,1,1,1,1,0,0)"
        )
        connection.execute(
            "INSERT INTO bookings "
            "(id,room_id,room_calendar_id,origin,external_reference,check_in,check_out,ical_uid,notes) "
            "VALUES (1,1,1,'housinganywhere','UID','2026-08-01','2026-08-05','ical-uid','Manualmente bloqueado')"
        )
        connection.commit()
    finally:
        connection.close()

    command.upgrade(config, "head")
    connection = sqlite3.connect(database_path)
    try:
        assert connection.execute(
            "SELECT last_seen_in_feed_at FROM bookings"
        ).fetchone() == (None,)
        assert connection.execute(
            "SELECT feed_presence_tracking_started_at FROM room_calendars"
        ).fetchone() == (None,)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()

    command.downgrade(config, MASTER_CALENDAR_OBSERVATION_REVISION)
    connection = sqlite3.connect(database_path)
    try:
        assert "last_seen_in_feed_at" not in {
            row[1] for row in connection.execute("PRAGMA table_info(bookings)")
        }
        assert "feed_presence_tracking_started_at" not in {
            row[1] for row in connection.execute("PRAGMA table_info(room_calendars)")
        }
        assert connection.execute("SELECT COUNT(*) FROM bookings").fetchone() == (1,)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()

    command.upgrade(config, "head")
    connection = sqlite3.connect(database_path)
    try:
        assert connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone() == (HEAD_REVISION,)
        assert connection.execute("SELECT COUNT(*) FROM bookings").fetchone() == (1,)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()


@pytest.mark.alembic_audit
def test_operational_intersection_triggers_upgrade_downgrade_upgrade(
    tmp_path, monkeypatch
):
    database_path = Path(tmp_path) / "operational_intersections.db"
    config, _database_url = configure_temporary_database(monkeypatch, database_path)
    command.upgrade(config, IMPORTED_PRESENCE_REVISION)
    connection = sqlite3.connect(database_path)
    database_session.register_sqlite_functions(connection)
    try:
        connection.execute(
            "INSERT INTO properties (id,name,address,city,owner,active) "
            "VALUES (1,'Piso','Calle','Madrid','Owner',1)"
        )
        connection.execute(
            "INSERT INTO rooms "
            "(id,property_id,code,display_order,base_price,active,master_calendar_token) "
            "VALUES (1,1,'R1',1,500,1,'token')"
        )
        connection.execute(
            "INSERT INTO bookings "
            "(id,room_id,origin,check_in,check_out,ical_uid) "
            "VALUES (1,1,'manual','2026-04-13','2026-05-31','ical-1')"
        )
        connection.commit()
    finally:
        connection.close()

    command.upgrade(config, "head")
    connection = sqlite3.connect(database_path)
    connection.create_function(
        "rentalmanager_business_date", 0, lambda: "2026-08-17"
    )
    try:
        connection.execute(
            "INSERT INTO bookings "
            "(id,room_id,origin,check_in,check_out,ical_uid) "
            "VALUES (2,1,'manual','2026-05-08','2026-08-31','ical-2')"
        )
        connection.commit()
        trigger_sql = connection.execute(
            "SELECT sql FROM sqlite_master "
            "WHERE type='trigger' AND name='trg_bookings_no_overlap_insert'"
        ).fetchone()[0]
        assert "MIN(existing.check_out, NEW.check_out)" in trigger_sql
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()

    command.downgrade(config, IMPORTED_PRESENCE_REVISION)
    connection = sqlite3.connect(database_path)
    try:
        assert connection.execute("SELECT COUNT(*) FROM bookings").fetchone() == (2,)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()

    command.upgrade(config, "head")
    connection = sqlite3.connect(database_path)
    try:
        assert connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone() == (HEAD_REVISION,)
        assert connection.execute("SELECT COUNT(*) FROM bookings").fetchone() == (2,)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()


@pytest.mark.alembic_audit
def test_public_listing_foundation_upgrade_downgrade_upgrade(
    tmp_path, monkeypatch
):
    database_path = Path(tmp_path) / "public_listing_foundation.db"
    config, _database_url = configure_temporary_database(monkeypatch, database_path)
    command.upgrade(config, OPERATIONAL_OVERLAP_REVISION)
    connection = sqlite3.connect(database_path)
    try:
        connection.execute(
            "INSERT INTO properties (id,name,address,city,owner,active) "
            "VALUES (1,'Piso','Dirección privada','Madrid','Owner',1)"
        )
        connection.execute(
            "INSERT INTO rooms "
            "(id,property_id,code,display_order,base_price,active,master_calendar_token) "
            "VALUES (1,1,'R1',1,500,1,'token')"
        )
        connection.commit()
    finally:
        connection.close()

    command.upgrade(config, "head")
    connection = sqlite3.connect(database_path)
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        assert connection.execute(
            "SELECT public_title,public_description,public_location,public_slug,is_published "
            "FROM properties WHERE id=1"
        ).fetchone() == (None, None, None, None, 0)
        assert connection.execute(
            "SELECT public_title,public_description,public_slug,is_published "
            "FROM rooms WHERE id=1"
        ).fetchone() == (None, None, None, 0)
        assert {
            "features", "property_features", "room_features", "media_assets",
            "property_photos", "room_photos",
        } <= {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }

        connection.execute(
            "INSERT INTO features "
            "(slug,name,scope,category,display_order,active) "
            "VALUES ('wifi','Wi-Fi','both','conectividad',0,1)"
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO features "
                "(slug,name,scope,category,display_order,active) "
                "VALUES ('bad','Bad','invalid','other',0,1)"
            )
        connection.execute(
            "INSERT INTO media_assets "
            "(id,storage_key,mime_type,width,height,byte_size,checksum_sha256,status,created_at) "
            "VALUES (1,'asset-1','image/webp',1600,900,1000,'checksum-1','ready','2026-08-20')"
        )
        connection.execute(
            "INSERT INTO media_assets "
            "(id,storage_key,mime_type,width,height,byte_size,checksum_sha256,status,created_at) "
            "VALUES (2,'asset-2','image/webp',1600,900,1000,'checksum-2','ready','2026-08-20')"
        )
        connection.execute(
            "INSERT INTO room_photos "
            "(id,room_id,media_asset_id,position,is_primary) VALUES (1,1,1,0,1)"
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO room_photos "
                "(id,room_id,media_asset_id,position,is_primary) VALUES (2,1,2,1,1)"
            )
        connection.rollback()

        connection.execute(
            "UPDATE properties SET public_slug='property-slug' WHERE id=1"
        )
        connection.execute(
            "UPDATE rooms SET public_slug='room-slug' WHERE id=1"
        )
        connection.commit()
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()

    command.downgrade(config, OPERATIONAL_OVERLAP_REVISION)
    connection = sqlite3.connect(database_path)
    try:
        assert "is_published" not in {
            row[1] for row in connection.execute("PRAGMA table_info(rooms)")
        }
        assert connection.execute("SELECT COUNT(*) FROM properties").fetchone() == (1,)
        assert connection.execute("SELECT COUNT(*) FROM rooms").fetchone() == (1,)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()

    command.upgrade(config, "head")
    connection = sqlite3.connect(database_path)
    try:
        assert connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone() == (HEAD_REVISION,)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
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
            HEAD_REVISION,
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
    connection = sqlite3.connect(
        f"file:{database_path.as_posix()}?mode=ro", uri=True
    )
    try:
        existing_tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        } & set(Base.metadata.tables)
    finally:
        connection.close()
    counts_before = table_counts(database_path, existing_tables)
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
            MASTER_CALENDAR_OBSERVATION_REVISION,
                IMPORTED_PRESENCE_REVISION,
                OPERATIONAL_OVERLAP_REVISION,
                PUBLICATION_FOUNDATION_REVISION,
                SHARED_BATHROOM_REVISION,
                FINANCIAL_LEDGER_REVISION,
                HEAD_REVISION,
        }
    finally:
        connection.close()

    command.upgrade(config, "head")
    command.current(config)

    assert table_counts(database_path, existing_tables) == counts_before
    assert schema_snapshot(database_path, ("properties",)) == roots_before
    if source_revision == HEAD_REVISION:
        assert file_hash(database_path) == copy_hash_before
    assert_schema_matches_models(database_url)
    connection = sqlite3.connect(f"file:{database_path.as_posix()}?mode=ro", uri=True)
    try:
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            HEAD_REVISION,
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
            HEAD_REVISION,
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
            HEAD_REVISION,
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
            HEAD_REVISION,
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
            HEAD_REVISION,
        )
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute(
            "SELECT consecutive_failures,automatic_sync_enabled FROM room_calendars"
        ).fetchone() == (0, 1)
    finally:
        connection.close()


@pytest.mark.alembic_audit
def test_optional_room_price_upgrade_downgrade_upgrade_preserves_existing_price(tmp_path, monkeypatch):
    database_path = Path(tmp_path) / "optional_room_price_round_trip.db"
    config, _database_url = configure_temporary_database(monkeypatch, database_path)
    command.upgrade(config, PUBLICATION_FOUNDATION_REVISION)
    connection = sqlite3.connect(database_path)
    try:
        connection.execute(
            "INSERT INTO properties (id,name,address,city,owner,active) "
            "VALUES (1,'Piso','Calle','Madrid','Owner',1)"
        )
        connection.execute(
            "INSERT INTO rooms (id,property_id,code,display_order,base_price,active,master_calendar_token) "
            "VALUES (1,1,'R1',1,500,1,'room-token')"
        )
        connection.commit()
    finally:
        connection.close()

    command.upgrade(config, "head")
    connection = sqlite3.connect(database_path)
    try:
        columns = {row[1]: row for row in connection.execute("PRAGMA table_info('rooms')")}
        assert columns["base_price"][3] == 0
        assert connection.execute("SELECT base_price FROM rooms WHERE id=1").fetchone()[0] == 500
    finally:
        connection.close()

    command.downgrade(config, PUBLICATION_FOUNDATION_REVISION)
    command.upgrade(config, "head")
    connection = sqlite3.connect(f"file:{database_path.as_posix()}?mode=ro", uri=True)
    try:
        columns = {row[1]: row for row in connection.execute("PRAGMA table_info('rooms')")}
        assert columns["base_price"][3] == 0
        assert connection.execute("SELECT base_price FROM rooms WHERE id=1").fetchone()[0] == 500
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()


@pytest.mark.alembic_audit
def test_optional_room_price_downgrade_is_blocked_when_null_prices_exist(tmp_path, monkeypatch):
    database_path = Path(tmp_path) / "optional_room_price_blocked_downgrade.db"
    config, _database_url = configure_temporary_database(monkeypatch, database_path)
    command.upgrade(config, "head")
    connection = sqlite3.connect(database_path)
    try:
        connection.execute(
            "INSERT INTO properties (id,name,address,city,owner,active) "
            "VALUES (1,'Piso','Calle','Madrid','Owner',1)"
        )
        connection.execute(
            "INSERT INTO rooms (id,property_id,code,display_order,base_price,active,master_calendar_token) "
            "VALUES (1,1,'R1',1,NULL,1,'room-token')"
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(RuntimeError, match="Downgrade blocked"):
        command.downgrade(config, PUBLICATION_FOUNDATION_REVISION)

    connection = sqlite3.connect(f"file:{database_path.as_posix()}?mode=ro", uri=True)
    try:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (OPTIONAL_ROOM_PRICE_REVISION,)
        assert connection.execute("SELECT base_price FROM rooms WHERE id=1").fetchone() == (None,)
    finally:
        connection.close()
