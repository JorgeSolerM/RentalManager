"""Remove per-platform RoomCalendar export URLs.

Revision ID: d4e8f1a2c703
Revises: c7d9e4a1b602
Create Date: 2026-08-16
"""

from alembic import op
import sqlalchemy as sa


revision = "d4e8f1a2c703"
down_revision = "c7d9e4a1b602"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    calendar_count = connection.execute(
        sa.text("SELECT COUNT(*) FROM room_calendars")
    ).scalar_one()
    if calendar_count:
        raise RuntimeError(
            "RoomCalendar export model migration requires an empty room_calendars table"
        )

    with op.batch_alter_table("room_calendars") as batch_op:
        batch_op.drop_column("export_url")


def downgrade() -> None:
    with op.batch_alter_table("room_calendars") as batch_op:
        batch_op.add_column(sa.Column("export_url", sa.String(500), nullable=True))
