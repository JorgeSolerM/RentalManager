"""Track imported Booking presence by successful feed synchronization.

Revision ID: d2f4a6b8c901
Revises: c9e1f3a5b607
Create Date: 2026-08-19
"""

import sqlalchemy as sa
from alembic import op


revision = "d2f4a6b8c901"
down_revision = "c9e1f3a5b607"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "bookings",
        sa.Column("last_seen_in_feed_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "room_calendars",
        sa.Column("feed_presence_tracking_started_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("room_calendars", "feed_presence_tracking_started_at")
    op.drop_column("bookings", "last_seen_in_feed_at")
