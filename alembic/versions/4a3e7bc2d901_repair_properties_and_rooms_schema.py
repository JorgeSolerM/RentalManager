"""Repair properties and rooms omitted from the initial schema.

Revision ID: 4a3e7bc2d901
Revises: 22a99ef8f2cb
Create Date: 2026-08-16
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "4a3e7bc2d901"
down_revision: Union[str, Sequence[str], None] = "22a99ef8f2cb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_index(table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(
        index["name"] == index_name
        for index in inspector.get_indexes(table_name)
    )


def upgrade() -> None:
    """Create only the tables omitted from the already-applied initial revision."""
    inspector = sa.inspect(op.get_bind())

    if not inspector.has_table("properties"):
        op.create_table(
            "properties",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=100), nullable=False),
            sa.Column("alias", sa.String(length=20), nullable=True),
            sa.Column("address", sa.String(length=255), nullable=False),
            sa.Column("city", sa.String(length=100), nullable=False),
            sa.Column("owner", sa.String(length=100), nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("active", sa.Boolean(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )

    if not _has_index("properties", "ix_properties_id"):
        op.create_index("ix_properties_id", "properties", ["id"], unique=False)

    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("rooms"):
        op.create_table(
            "rooms",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("property_id", sa.Integer(), nullable=False),
            sa.Column("code", sa.String(length=20), nullable=False),
            sa.Column("display_order", sa.Integer(), nullable=False),
            sa.Column("base_price", sa.Numeric(precision=10, scale=2), nullable=False),
            sa.Column("square_meters", sa.Numeric(precision=5, scale=2), nullable=True),
            sa.Column("active", sa.Boolean(), nullable=False),
            sa.ForeignKeyConstraint(["property_id"], ["properties.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    if not _has_index("rooms", "ix_rooms_id"):
        op.create_index("ix_rooms_id", "rooms", ["id"], unique=False)


def downgrade() -> None:
    raise RuntimeError(
        "Downgrade is intentionally unsupported: restore a database backup "
        "to reverse this schema repair without risking historical data."
    )
