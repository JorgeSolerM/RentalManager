"""Add local expected arrival and departure dates to bookings.

Revision ID: d7f9b1c3e548
Revises: c6e8a0b2d437
"""

from alembic import op
import sqlalchemy as sa


revision = "d7f9b1c3e548"
down_revision = "c6e8a0b2d437"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "bookings",
        sa.Column("expected_arrival_date", sa.Date(), nullable=True),
    )
    op.add_column(
        "bookings",
        sa.Column("expected_departure_date", sa.Date(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("bookings", "expected_departure_date")
    op.drop_column("bookings", "expected_arrival_date")
