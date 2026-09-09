"""Persistent per-creditor mandate reference counter."""
from alembic import op
import sqlalchemy as sa

revision = "e7a9b1c3d560"
down_revision = "d6f8a0b2c459"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("sepa_creditor_profiles", sa.Column("mandate_reference_counter", sa.Integer(), nullable=False, server_default="0"))


def downgrade():
    op.drop_column("sepa_creditor_profiles", "mandate_reference_counter")
