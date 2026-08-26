"""add explicit room operational start date

Revision ID: e1c3a5b7d902
Revises: d7f9b1c3e548
Create Date: 2026-08-26
"""

from alembic import op
import sqlalchemy as sa


revision = "e1c3a5b7d902"
down_revision = "d7f9b1c3e548"
branch_labels = None
depends_on = None


# Technical preservation date: all Rooms at the prior head were already treated
# as operational. It is deliberately not an inferred historical start date.
BACKFILL_DATE = "2026-08-26"


def upgrade() -> None:
    op.add_column("rooms", sa.Column("operational_since", sa.Date(), nullable=True))
    op.execute(
        sa.text("UPDATE rooms SET operational_since = :backfill_date").bindparams(
            backfill_date=BACKFILL_DATE
        )
    )


def downgrade() -> None:
    # SQLite supports direct DROP COLUMN here. Avoid batch table recreation:
    # rooms is referenced by bookings and room_calendars with FKs enabled.
    op.drop_column("rooms", "operational_since")
