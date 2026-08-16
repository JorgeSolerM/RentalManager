"""Add imported-booking identity and strict overlap safeguards.

Revision ID: c7d9e4a1b602
Revises: 4a3e7bc2d901
Create Date: 2026-08-16
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c7d9e4a1b602"
down_revision: Union[str, Sequence[str], None] = "4a3e7bc2d901"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEX_NAME = "uq_bookings_calendar_external_reference"
INSERT_TRIGGER = "trg_bookings_no_overlap_insert"
UPDATE_TRIGGER = "trg_bookings_no_overlap_update"


def _assert_historical_data_is_safe() -> None:
    connection = op.get_bind()
    duplicate = connection.execute(sa.text("""
        SELECT room_calendar_id, external_reference
        FROM bookings
        WHERE room_calendar_id IS NOT NULL
          AND external_reference IS NOT NULL
        GROUP BY room_calendar_id, external_reference
        HAVING COUNT(*) > 1
        LIMIT 1
    """)).first()
    if duplicate is not None:
        raise RuntimeError(
            "Cannot add imported-booking identity: duplicate external references exist."
        )

    overlap = connection.execute(sa.text("""
        SELECT first_booking.id, second_booking.id
        FROM bookings AS first_booking
        JOIN bookings AS second_booking
          ON first_booking.room_id = second_booking.room_id
         AND first_booking.id < second_booking.id
         AND first_booking.check_in < second_booking.check_out
         AND first_booking.check_out > second_booking.check_in
        LIMIT 1
    """)).first()
    if overlap is not None:
        raise RuntimeError(
            "Cannot add booking overlap triggers: historical overlaps exist."
        )


def upgrade() -> None:
    _assert_historical_data_is_safe()
    op.create_index(
        INDEX_NAME,
        "bookings",
        ["room_calendar_id", "external_reference"],
        unique=True,
        sqlite_where=sa.text(
            "room_calendar_id IS NOT NULL AND external_reference IS NOT NULL"
        ),
    )
    op.execute(f"""
        CREATE TRIGGER {INSERT_TRIGGER}
        BEFORE INSERT ON bookings
        WHEN EXISTS (
            SELECT 1
            FROM bookings AS existing
            WHERE existing.room_id = NEW.room_id
              AND existing.check_in < NEW.check_out
              AND existing.check_out > NEW.check_in
        )
        BEGIN
            SELECT RAISE(ABORT, 'booking_overlap');
        END
    """)
    op.execute(f"""
        CREATE TRIGGER {UPDATE_TRIGGER}
        BEFORE UPDATE OF room_id, check_in, check_out ON bookings
        WHEN EXISTS (
            SELECT 1
            FROM bookings AS existing
            WHERE existing.room_id = NEW.room_id
              AND existing.id != NEW.id
              AND existing.check_in < NEW.check_out
              AND existing.check_out > NEW.check_in
        )
        BEGIN
            SELECT RAISE(ABORT, 'booking_overlap');
        END
    """)


def downgrade() -> None:
    op.execute(f"DROP TRIGGER IF EXISTS {UPDATE_TRIGGER}")
    op.execute(f"DROP TRIGGER IF EXISTS {INSERT_TRIGGER}")
    op.drop_index(INDEX_NAME, table_name="bookings")
