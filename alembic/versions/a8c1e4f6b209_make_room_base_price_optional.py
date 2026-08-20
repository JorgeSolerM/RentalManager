"""Allow rooms to be created before their commercial price is configured.

Revision ID: a8c1e4f6b209
Revises: f6b8d0e2a413
Create Date: 2026-08-20
"""

import sqlalchemy as sa
from alembic import op


revision = "a8c1e4f6b209"
down_revision = "f6b8d0e2a413"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
    with op.batch_alter_table("rooms") as batch_op:
        batch_op.alter_column(
            "base_price",
            existing_type=sa.Numeric(precision=10, scale=2),
            nullable=True,
        )
    if connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall():
        raise RuntimeError("Optional Room price migration produced foreign key violations")


def downgrade() -> None:
    connection = op.get_bind()
    null_prices = connection.scalar(
        sa.text("SELECT COUNT(*) FROM rooms WHERE base_price IS NULL")
    )
    if null_prices:
        raise RuntimeError(
            "Downgrade blocked: rooms.base_price contains NULL values. "
            "Configure every Room price before downgrading."
        )
    connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
    with op.batch_alter_table("rooms") as batch_op:
        batch_op.alter_column(
            "base_price",
            existing_type=sa.Numeric(precision=10, scale=2),
            nullable=False,
        )
    if connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall():
        raise RuntimeError("Optional Room price downgrade produced foreign key violations")
