"""Base operational Booking overlaps on the real intersection.

Revision ID: e3a5c7d9f102
Revises: d2f4a6b8c901
Create Date: 2026-08-19
"""

from alembic import op


revision = "e3a5c7d9f102"
down_revision = "d2f4a6b8c901"
branch_labels = None
depends_on = None


def _drop_overlap_triggers() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_bookings_no_overlap_update")
    op.execute("DROP TRIGGER IF EXISTS trg_bookings_no_overlap_insert")


def _create_intersection_overlap_triggers() -> None:
    op.execute("""
        CREATE TRIGGER trg_bookings_no_overlap_insert
        BEFORE INSERT ON bookings
        WHEN EXISTS (
            SELECT 1 FROM bookings AS existing
            WHERE existing.room_id = NEW.room_id
              AND existing.check_in < NEW.check_out
              AND existing.check_out > NEW.check_in
              AND MIN(existing.check_out, NEW.check_out)
                    > rentalmanager_business_date()
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
              AND MIN(existing.check_out, NEW.check_out)
                    > rentalmanager_business_date()
        )
        BEGIN
            SELECT RAISE(ABORT, 'booking_overlap');
        END
    """)


def _create_asymmetric_overlap_triggers() -> None:
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


def upgrade() -> None:
    _drop_overlap_triggers()
    _create_intersection_overlap_triggers()


def downgrade() -> None:
    _drop_overlap_triggers()
    _create_asymmetric_overlap_triggers()
