"""Non-destructive manual receipt registration and SEPA returns/cancellation."""
from alembic import op
import sqlalchemy as sa

revision = 'a9c1e3f5b782'
down_revision = 'f8b0d2e4a671'
branch_labels = None
depends_on = None

OLD_COLLECTION = "(status = 'collected' AND payment_id IS NOT NULL AND collected_at IS NOT NULL) OR (status != 'collected' AND payment_id IS NULL AND collected_at IS NULL)"
NEW_COLLECTION = "(status IN ('collected','returned') AND payment_id IS NOT NULL AND collected_at IS NOT NULL) OR (status NOT IN ('collected','returned') AND payment_id IS NULL AND collected_at IS NULL)"


def _foreign_keys(enabled):
    # SQLite cannot toggle this pragma inside a transaction. A dedicated Alembic
    # connection is used; no application connection or global setting is changed.
    with op.get_context().autocommit_block():
        op.get_bind().exec_driver_sql('PRAGMA foreign_keys=' + ('ON' if enabled else 'OFF'))


def _check():
    if op.get_bind().exec_driver_sql('PRAGMA foreign_key_check').fetchall():
        raise RuntimeError('SEPA migration integrity failure')
    _foreign_keys(True)


def upgrade():
    _foreign_keys(False)
    with op.batch_alter_table('sepa_batches') as batch:
        batch.drop_constraint('ck_sepa_batches_status',type_='check')
        batch.create_check_constraint('ck_sepa_batches_status', "status IN ('prepared','exported','presented','partially_collected','collected','cancelled')")
    with op.batch_alter_table('sepa_debits') as batch:
        batch.add_column(sa.Column('return_payment_id',sa.Integer(),nullable=True))
        batch.add_column(sa.Column('returned_on',sa.Date(),nullable=True))
        batch.add_column(sa.Column('returned_at',sa.DateTime(),nullable=True))
        batch.add_column(sa.Column('return_reason',sa.String(255),nullable=True))
        batch.add_column(sa.Column('cancelled_at',sa.DateTime(),nullable=True))
        batch.add_column(sa.Column('cancellation_reason',sa.String(255),nullable=True))
        batch.create_foreign_key('fk_sepa_return_payment','payments',['return_payment_id'],['id'],ondelete='RESTRICT')
        batch.create_unique_constraint('uq_sepa_return_payment',['return_payment_id'])
        batch.drop_constraint('ck_sepa_debit_status',type_='check')
        batch.drop_constraint('ck_sepa_debit_collection',type_='check')
        batch.create_check_constraint('ck_sepa_debit_status',"status IN ('prepared','presented','collected','returned','cancelled')")
        batch.create_check_constraint('ck_sepa_debit_collection',NEW_COLLECTION)
        batch.create_check_constraint('ck_sepa_debit_return',"(status = 'returned' AND return_payment_id IS NOT NULL AND returned_on IS NOT NULL AND returned_at IS NOT NULL) OR (status != 'returned' AND return_payment_id IS NULL AND returned_on IS NULL AND returned_at IS NULL)")
        batch.create_check_constraint('ck_sepa_debit_cancel',"(status = 'cancelled' AND cancelled_at IS NOT NULL) OR (status != 'cancelled' AND cancelled_at IS NULL)")
    op.create_table('payment_registrations',
        sa.Column('request_key',sa.String(36),primary_key=True),
        sa.Column('fingerprint',sa.String(64),nullable=False),
        sa.Column('payment_id',sa.Integer(),sa.ForeignKey('payments.id',ondelete='RESTRICT'),nullable=False,unique=True))
    _check()


def downgrade():
    connection=op.get_bind()
    if connection.execute(sa.text("SELECT 1 FROM sepa_debits WHERE status IN ('returned','cancelled') LIMIT 1")).first() or connection.execute(sa.text('SELECT 1 FROM payment_registrations LIMIT 1')).first():
        raise RuntimeError('Downgrade blocked: preserve return/cancellation/payment registration history')
    _foreign_keys(False)
    op.drop_table('payment_registrations')
    with op.batch_alter_table('sepa_debits') as batch:
        for name in ('ck_sepa_debit_status','ck_sepa_debit_collection','ck_sepa_debit_return','ck_sepa_debit_cancel'):
            batch.drop_constraint(name,type_='check')
        batch.drop_constraint('fk_sepa_return_payment',type_='foreignkey')
        batch.drop_constraint('uq_sepa_return_payment',type_='unique')
        for name in ('return_payment_id','returned_on','returned_at','return_reason','cancelled_at','cancellation_reason'):
            batch.drop_column(name)
        batch.create_check_constraint('ck_sepa_debit_status',"status IN ('prepared','presented','collected')")
        batch.create_check_constraint('ck_sepa_debit_collection',OLD_COLLECTION)
    with op.batch_alter_table('sepa_batches') as batch:
        batch.drop_constraint('ck_sepa_batches_status',type_='check')
        batch.create_check_constraint('ck_sepa_batches_status',"status IN ('prepared','exported','presented','partially_collected','collected')")
    _check()
