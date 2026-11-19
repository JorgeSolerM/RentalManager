"""Audited receipt cancellation and replacement; no fiscal dependency."""
from alembic import op
import sqlalchemy as sa
revision = 'e45b6d10278c'
down_revision = 'd34a5c0f167b'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('payment_correction_operations',
        sa.Column('request_key',sa.String(36),primary_key=True),
        sa.Column('original_payment_id',sa.Integer(),sa.ForeignKey('payments.id',ondelete='RESTRICT'),nullable=False,unique=True),
        sa.Column('replacement_payment_id',sa.Integer(),sa.ForeignKey('payments.id',ondelete='RESTRICT'),nullable=True,unique=True),
        sa.Column('kind',sa.String(10),nullable=False),sa.Column('reason',sa.Text(),nullable=False),
        sa.Column('before_amount',sa.Numeric(12,2),nullable=False),sa.Column('after_amount',sa.Numeric(12,2),nullable=False),
        sa.Column('fingerprint',sa.String(64),nullable=False),sa.Column('reviewed_state',sa.String(64),nullable=False),
        sa.Column('distribution',sa.JSON(),nullable=False),sa.Column('custody_snapshot',sa.JSON(),nullable=False),
        sa.Column('created_at',sa.DateTime(),nullable=False,server_default=sa.func.current_timestamp()),
        sa.CheckConstraint("kind IN ('void','replace')",name='ck_payment_correction_kind'),
        sa.CheckConstraint('before_amount > 0 AND after_amount >= 0',name='ck_payment_correction_amounts'),
        sa.CheckConstraint("(kind='void' AND replacement_payment_id IS NULL AND after_amount=0) OR (kind='replace' AND replacement_payment_id IS NOT NULL AND after_amount>0)",name='ck_payment_correction_replacement'),
        sa.CheckConstraint('length(trim(reason)) > 0',name='ck_payment_correction_reason'))
    for event in ('UPDATE','DELETE'):
        op.execute(f"CREATE TRIGGER correction_audit_no_{event.lower()} BEFORE {event} ON payment_correction_operations BEGIN SELECT RAISE(ABORT,'correction_audit_immutable'); END")
    op.execute("""CREATE TRIGGER corrected_payment_immutable BEFORE UPDATE ON payments
        WHEN EXISTS(SELECT 1 FROM payment_correction_operations WHERE original_payment_id=OLD.id)
        BEGIN SELECT RAISE(ABORT,'corrected_payment_immutable'); END""")
    for event, condition in (
        ('insert','original_payment_id=NEW.payment_id'),
        ('update','original_payment_id=OLD.payment_id OR original_payment_id=NEW.payment_id'),
        ('delete','original_payment_id=OLD.payment_id')):
        op.execute(f"""CREATE TRIGGER corrected_allocations_no_{event} BEFORE {event.upper()} ON payment_allocations
            WHEN EXISTS(SELECT 1 FROM payment_correction_operations WHERE {condition})
            BEGIN SELECT RAISE(ABORT,'corrected_allocations_immutable'); END""")


def downgrade():
    if op.get_bind().execute(sa.text('SELECT count(*) FROM payment_correction_operations')).scalar():
        raise RuntimeError('No se elimina el historial de correcciones existente.')
    for name in ['correction_audit_no_update','correction_audit_no_delete','corrected_payment_immutable',
                 'corrected_allocations_no_insert','corrected_allocations_no_update','corrected_allocations_no_delete']:
        op.execute('DROP TRIGGER '+name)
    op.drop_table('payment_correction_operations')
