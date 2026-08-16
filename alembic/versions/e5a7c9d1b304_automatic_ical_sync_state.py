"""Add automatic iCal synchronization operational state.

Revision ID: e5a7c9d1b304
Revises: a6f3b9c8d210
Create Date: 2026-08-16
"""

from alembic import op
import sqlalchemy as sa


revision = "e5a7c9d1b304"
down_revision = "a6f3b9c8d210"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "room_calendars",
        sa.Column("last_sync_attempt_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "room_calendars",
        sa.Column("last_sync_status", sa.String(20), nullable=True),
    )
    op.add_column(
        "room_calendars",
        sa.Column("last_sync_error", sa.String(100), nullable=True),
    )
    op.add_column(
        "room_calendars",
        sa.Column(
            "consecutive_failures",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "room_calendars",
        sa.Column(
            "automatic_sync_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )


def downgrade() -> None:
    connection = op.get_bind()
    connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
    with op.batch_alter_table("room_calendars") as batch_op:
        batch_op.drop_column("automatic_sync_enabled")
        batch_op.drop_column("consecutive_failures")
        batch_op.drop_column("last_sync_error")
        batch_op.drop_column("last_sync_status")
        batch_op.drop_column("last_sync_attempt_at")
    if connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall():
        raise RuntimeError("Automatic sync downgrade produced foreign key violations")
