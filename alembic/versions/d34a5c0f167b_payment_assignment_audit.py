"""Audited assignments of existing receipts; independent of fiscal branch."""
from alembic import op
import sqlalchemy as sa
revision = 'd34a5c0f167b'
down_revision = 'c2394bfe056a'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('payment_allocation_operations',
        sa.Column('request_key',sa.String(36),primary_key=True),
        sa.Column('payment_id',sa.Integer(),sa.ForeignKey('payments.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('fingerprint',sa.String(64),nullable=False),
        sa.Column('reviewed_state',sa.String(64),nullable=False),
        sa.Column('amount',sa.Numeric(12,2),nullable=False),
        sa.Column('changes',sa.JSON(),nullable=False),
        sa.Column('created_at',sa.DateTime(),nullable=False,server_default=sa.func.current_timestamp()),
        sa.CheckConstraint('amount > 0',name='ck_allocation_operation_positive'))
    op.create_index('ix_payment_allocation_operations_payment_id','payment_allocation_operations',['payment_id'])
    for event in ('UPDATE','DELETE'):
        op.execute(f"CREATE TRIGGER allocation_operation_no_{event.lower()} BEFORE {event} ON payment_allocation_operations BEGIN SELECT RAISE(ABORT,'allocation_audit_immutable'); END")


def downgrade():
    if op.get_bind().execute(sa.text('SELECT count(*) FROM payment_allocation_operations')).scalar():
        raise RuntimeError('No se elimina la trazabilidad de asignaciones existentes.')
    for event in ('update','delete'):
        op.execute(f'DROP TRIGGER allocation_operation_no_{event}')
    op.drop_table('payment_allocation_operations')
