"""Add the optional reference IBAN to people.

Revision ID: b4d6f8a0c237
Revises: a3c5e7f9b126
"""
from alembic import op
import sqlalchemy as sa


revision = "b4d6f8a0c237"
down_revision = "a3c5e7f9b126"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("persons", sa.Column("iban", sa.String(34), nullable=True))


def downgrade():
    op.drop_column("persons", "iban")
