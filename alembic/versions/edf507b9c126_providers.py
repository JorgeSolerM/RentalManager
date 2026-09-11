"""Private provider directory and optional structured expense supplier."""
from alembic import op
import sqlalchemy as sa

revision = 'edf507b9c126'
down_revision = 'dce4f6a8b015'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('providers',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('legal_name',sa.String(180),nullable=False),
        *[sa.Column(name,sa.String(length),nullable=True) for name,length in
          [('tax_id',40),('address_line',255),('postal_code',20),('city',120),('province',120),
           ('country',2),('phone',40),('email',254),('iban',34)]],
        sa.Column('default_expense_category_id',sa.Integer(),sa.ForeignKey('expense_categories.id',ondelete='RESTRICT')),
        sa.Column('notes',sa.Text()),
        sa.Column('active',sa.Boolean(),nullable=False,server_default='1'),
        sa.Column('created_at',sa.DateTime(),nullable=False,server_default=sa.func.current_timestamp()),
        sa.Column('updated_at',sa.DateTime(),nullable=False,server_default=sa.func.current_timestamp()),
        sa.CheckConstraint('length(trim(legal_name)) > 0',name='ck_provider_name'),
        sa.CheckConstraint('country IS NULL OR (length(country) = 2 AND country = upper(country))',name='ck_provider_country'))
    # Native nullable ADD COLUMN avoids rebuilding a table referenced by immutable
    # payment/settlement history. No backfill and no trigger removal.
    op.execute('ALTER TABLE expenses ADD COLUMN provider_id INTEGER REFERENCES providers(id) ON DELETE RESTRICT')
    op.add_column('expenses',sa.Column('provider_snapshot',sa.JSON(none_as_null=True),nullable=True))
    op.create_index('ix_expenses_provider_id','expenses',['provider_id'])


def downgrade():
    db = op.get_bind()
    if db.scalar(sa.text('SELECT count(*) FROM providers')) or db.scalar(sa.text("SELECT count(*) FROM expenses WHERE provider_id IS NOT NULL OR (provider_snapshot IS NOT NULL AND provider_snapshot != 'null')")):
        raise RuntimeError('No se elimina información de proveedores: downgrade bloqueado con datos.')
    op.drop_index('ix_expenses_provider_id',table_name='expenses')
    op.drop_column('expenses','provider_snapshot')
    op.drop_column('expenses','provider_id')
    op.drop_table('providers')
