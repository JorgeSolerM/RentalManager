"""Store aggregate master calendar request observations.

Revision ID: c9e1f3a5b607
Revises: f8b2d4e6a405
Create Date: 2026-08-17
"""

import sqlalchemy as sa
from alembic import op


revision = "c9e1f3a5b607"
down_revision = "f8b2d4e6a405"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("room_calendars", sa.Column(
        "master_calendar_first_request_at", sa.DateTime(), nullable=True
    ))
    op.add_column("room_calendars", sa.Column(
        "last_master_calendar_request_at", sa.DateTime(), nullable=True
    ))
    op.add_column("room_calendars", sa.Column(
        "master_calendar_request_count",
        sa.Integer(),
        nullable=False,
        server_default="0",
    ))


def downgrade() -> None:
    op.drop_column("room_calendars", "master_calendar_request_count")
    op.drop_column("room_calendars", "last_master_calendar_request_at")
    op.drop_column("room_calendars", "master_calendar_first_request_at")
