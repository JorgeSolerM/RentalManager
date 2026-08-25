"""Add structured shared bathroom counts to properties.

Revision ID: c6e8a0b2d437
Revises: b3d5f7a9c124
"""

from alembic import op
import sqlalchemy as sa


revision = "c6e8a0b2d437"
down_revision = "b3d5f7a9c124"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "properties",
        sa.Column(
            "shared_full_bathroom_count",
            sa.Integer(),
            sa.CheckConstraint(
                "shared_full_bathroom_count IS NULL "
                "OR shared_full_bathroom_count >= 0",
                name="ck_properties_shared_full_bathroom_count_nonnegative",
            ),
            nullable=True,
        ),
    )
    op.add_column(
        "properties",
        sa.Column(
            "shared_toilet_count",
            sa.Integer(),
            sa.CheckConstraint(
                "shared_toilet_count IS NULL OR shared_toilet_count >= 0",
                name="ck_properties_shared_toilet_count_nonnegative",
            ),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("properties", "shared_toilet_count")
    op.drop_column("properties", "shared_full_bathroom_count")
