"""Add secure master room calendar identities.

Revision ID: a6f3b9c8d210
Revises: d4e8f1a2c703
Create Date: 2026-08-16
"""

import secrets
import uuid

from alembic import op
import sqlalchemy as sa


revision = "a6f3b9c8d210"
down_revision = "d4e8f1a2c703"
branch_labels = None
depends_on = None

ROOM_TOKEN_INDEX = "uq_rooms_master_calendar_token"
BOOKING_UID_INDEX = "uq_bookings_ical_uid"


def _recreate_overlap_triggers() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_bookings_no_overlap_update")
    op.execute("DROP TRIGGER IF EXISTS trg_bookings_no_overlap_insert")
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
    connection = op.get_bind()
    connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
    op.add_column(
        "rooms",
        sa.Column("master_calendar_token", sa.String(64), nullable=True),
    )
    op.add_column(
        "bookings",
        sa.Column("ical_uid", sa.String(64), nullable=True),
    )

    room_ids = connection.execute(sa.text("SELECT id FROM rooms")).scalars().all()
    for room_id in room_ids:
        connection.execute(
            sa.text(
                "UPDATE rooms SET master_calendar_token = :token WHERE id = :id"
            ),
            {"token": secrets.token_urlsafe(32), "id": room_id},
        )

    booking_ids = connection.execute(sa.text("SELECT id FROM bookings")).scalars().all()
    for booking_id in booking_ids:
        connection.execute(
            sa.text("UPDATE bookings SET ical_uid = :uid WHERE id = :id"),
            {"uid": uuid.uuid4().hex, "id": booking_id},
        )

    with op.batch_alter_table("rooms") as batch_op:
        batch_op.alter_column(
            "master_calendar_token",
            existing_type=sa.String(64),
            nullable=False,
        )
    with op.batch_alter_table("bookings") as batch_op:
        batch_op.alter_column(
            "ical_uid",
            existing_type=sa.String(64),
            nullable=False,
        )

    _recreate_overlap_triggers()
    op.create_index(
        ROOM_TOKEN_INDEX,
        "rooms",
        ["master_calendar_token"],
        unique=True,
    )
    op.create_index(
        BOOKING_UID_INDEX,
        "bookings",
        ["ical_uid"],
        unique=True,
    )
    if connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall():
        raise RuntimeError("Master calendar migration produced foreign key violations")


def downgrade() -> None:
    connection = op.get_bind()
    connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
    op.drop_index(BOOKING_UID_INDEX, table_name="bookings")
    op.drop_index(ROOM_TOKEN_INDEX, table_name="rooms")

    with op.batch_alter_table("bookings") as batch_op:
        batch_op.drop_column("ical_uid")
    _recreate_overlap_triggers()
    with op.batch_alter_table("rooms") as batch_op:
        batch_op.drop_column("master_calendar_token")
    if connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall():
        raise RuntimeError("Master calendar downgrade produced foreign key violations")
