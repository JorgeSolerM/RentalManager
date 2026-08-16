"""Allow reconstruction of a historical Booking despite overlaps.

Revision ID: f8b2d4e6a405
Revises: e5a7c9d1b304
Create Date: 2026-08-16
"""

from alembic import op


revision = "f8b2d4e6a405"
down_revision = "e5a7c9d1b304"
branch_labels = None
depends_on = None


def _drop_overlap_triggers() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_bookings_no_overlap_update")
    op.execute("DROP TRIGGER IF EXISTS trg_bookings_no_overlap_insert")


def _create_historical_overlap_triggers() -> None:
    op.execute("""
        CREATE TRIGGER trg_bookings_no_overlap_insert
        BEFORE INSERT ON bookings
        WHEN NEW.check_out >= rentalmanager_business_date()
         AND EXISTS (
            SELECT 1 FROM bookings AS existing
            WHERE existing.room_id = NEW.room_id
              AND existing.check_in < NEW.check_out
              AND existing.check_out > NEW.check_in
        )
        BEGIN
            SELECT RAISE(ABORT, 'booking_overlap');
        END
    """)
    op.execute("""
        CREATE TRIGGER trg_bookings_no_overlap_update
        BEFORE UPDATE OF room_id, check_in, check_out ON bookings
        WHEN NEW.check_out >= rentalmanager_business_date()
         AND EXISTS (
            SELECT 1 FROM bookings AS existing
            WHERE existing.room_id = NEW.room_id
              AND existing.id != NEW.id
              AND existing.check_in < NEW.check_out
              AND existing.check_out > NEW.check_in
        )
        BEGIN
            SELECT RAISE(ABORT, 'booking_overlap');
        END
    """)


def _create_strict_overlap_triggers() -> None:
    op.execute("""
        CREATE TRIGGER trg_bookings_no_overlap_insert
        BEFORE INSERT ON bookings
        WHEN EXISTS (
            SELECT 1 FROM bookings AS existing
            WHERE existing.room_id = NEW.room_id
              AND existing.check_in < NEW.check_out
              AND existing.check_out > NEW.check_in
        )
        BEGIN
            SELECT RAISE(ABORT, 'booking_overlap');
        END
    """)
    op.execute("""
        CREATE TRIGGER trg_bookings_no_overlap_update
        BEFORE UPDATE OF room_id, check_in, check_out ON bookings
        WHEN EXISTS (
            SELECT 1 FROM bookings AS existing
            WHERE existing.room_id = NEW.room_id
              AND existing.id != NEW.id
              AND existing.check_in < NEW.check_out
              AND existing.check_out > NEW.check_in
        )
        BEGIN
            SELECT RAISE(ABORT, 'booking_overlap');
        END
    """)


def upgrade() -> None:
    _drop_overlap_triggers()
    _create_historical_overlap_triggers()


def downgrade() -> None:
    connection = op.get_bind()
    conflicts = connection.exec_driver_sql("""
        SELECT 1
        FROM bookings AS first_booking
        JOIN bookings AS second_booking
          ON first_booking.id < second_booking.id
         AND first_booking.room_id = second_booking.room_id
         AND first_booking.check_in < second_booking.check_out
         AND first_booking.check_out > second_booking.check_in
        LIMIT 1
    """).fetchone()
    if conflicts is not None:
        raise RuntimeError(
            "Cannot restore strict overlap triggers while historical overlaps exist"
        )
    _drop_overlap_triggers()
    _create_strict_overlap_triggers()
