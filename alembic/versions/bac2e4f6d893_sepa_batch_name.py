"""Optional administrative batch name, independent of banking identifiers."""
from alembic import op
import sqlalchemy as sa

revision = 'bac2e4f6d893'
down_revision = 'a9c1e3f5b782'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('sepa_batches', sa.Column('name', sa.String(160), nullable=True))


def downgrade():
    # Native SQLite DROP COLUMN avoids rebuilding a table referenced by banking history.
    op.drop_column('sepa_batches', 'name')
