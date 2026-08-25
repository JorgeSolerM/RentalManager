"""Add the Manager public contact phone.

Revision ID: d5f7a9c1e326
Revises: c4e6a8b0d214
"""

import sqlalchemy as sa
from alembic import op


revision = "d5f7a9c1e326"
down_revision = "c4e6a8b0d214"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("managers", sa.Column("phone", sa.String(40), nullable=True))


def downgrade() -> None:
    op.drop_column("managers", "phone")
