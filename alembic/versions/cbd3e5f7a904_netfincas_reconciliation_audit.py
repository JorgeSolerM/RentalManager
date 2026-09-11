"""Minimal provenance for explicitly approved reconciliation writes (no backfill)."""
from alembic import op
import sqlalchemy as sa

revision = 'cbd3e5f7a904'
down_revision = 'bac2e4f6d893'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('migration_runs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('source', sa.String(30), nullable=False),
        sa.Column('source_digest', sa.String(64), nullable=False),
        sa.Column('plan_digest', sa.String(64), nullable=False),
        sa.Column('result', sa.String(20), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False))
    op.create_table('migration_actions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('run_id', sa.String(36), sa.ForeignKey('migration_runs.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('action_key', sa.String(64), nullable=False),
        sa.Column('source_id', sa.String(100), nullable=False),
        sa.Column('entity', sa.String(40), nullable=False),
        sa.Column('target_id', sa.Integer(), nullable=False),
        sa.Column('operation', sa.String(20), nullable=False),
        sa.Column('field', sa.String(40), nullable=False),
        sa.Column('result', sa.String(20), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.UniqueConstraint('action_key', name='uq_migration_action_key'))


def downgrade():
    if op.get_bind().execute(sa.text('SELECT COUNT(*) FROM migration_runs')).scalar():
        raise RuntimeError('La auditoría contiene ejecuciones: conservar trazabilidad antes de retirar el módulo.')
    op.drop_table('migration_actions')
    op.drop_table('migration_runs')
