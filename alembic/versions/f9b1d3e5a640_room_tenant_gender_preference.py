"""Add Room tenant gender preference.

Revision ID: f9b1d3e5a640
Revises: e7a9c1d3f428
"""

import sqlalchemy as sa
from alembic import op


revision = "f9b1d3e5a640"
down_revision = "e7a9c1d3f428"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "rooms",
        sa.Column(
            "tenant_gender_preference",
            sa.String(10),
            sa.CheckConstraint(
                "tenant_gender_preference IS NULL OR "
                "tenant_gender_preference IN ('any', 'male', 'female')",
                name="ck_rooms_tenant_gender_preference",
            ),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("rooms", "tenant_gender_preference")
