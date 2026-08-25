"""Remove obsolete Property couples policy.

Revision ID: b3d5f7a9c124
Revises: a2c4e6f8b013
"""

import sqlalchemy as sa
from alembic import op


revision = "b3d5f7a9c124"
down_revision = "a2c4e6f8b013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    configured = connection.execute(
        sa.text(
            "SELECT COUNT(*) FROM properties "
            "WHERE couples_allowed IS NOT NULL"
        )
    ).scalar_one()
    if configured:
        raise RuntimeError(
            "Cannot remove properties.couples_allowed while configured values exist."
        )
    op.drop_column("properties", "couples_allowed")


def downgrade() -> None:
    op.add_column(
        "properties",
        sa.Column("couples_allowed", sa.Boolean(), nullable=True),
    )
