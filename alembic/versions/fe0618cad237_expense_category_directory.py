"""Editable metadata for the existing shared expense category catalogue."""
from alembic import op
import sqlalchemy as sa

revision = 'fe0618cad237'
down_revision = 'edf507b9c126'
branch_labels = None
depends_on = None


def upgrade():
    # Native ADD COLUMN: never rebuild the parent of existing expense/provider FKs.
    op.add_column('expense_categories', sa.Column('description', sa.Text(), nullable=True))
    op.add_column('expense_categories', sa.Column('sort_order', sa.Integer(), nullable=True))
    op.add_column('expense_categories', sa.Column('created_at', sa.DateTime(), nullable=True))
    op.add_column('expense_categories', sa.Column('updated_at', sa.DateTime(), nullable=True))
    # Catalogue tracking starts here; these are not claimed historical creation dates.
    op.execute('UPDATE expense_categories SET created_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP')


def downgrade():
    db = op.get_bind()
    if db.scalar(sa.text('SELECT count(*) FROM expense_categories WHERE description IS NOT NULL OR sort_order IS NOT NULL')):
        raise RuntimeError('Downgrade bloqueado: existen metadatos de categorías que deben conservarse.')
    for column in ('updated_at', 'created_at', 'sort_order', 'description'):
        op.drop_column('expense_categories', column)
