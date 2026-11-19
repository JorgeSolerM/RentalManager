"""Audited expense revisions and administrative payment voids (economic branch)."""
from alembic import op
import sqlalchemy as sa
revision = 'f56c7e21389d'
down_revision = 'e45b6d10278c'
branch_labels = None
depends_on = None

TABLES = ('expense_payment_void_operations', 'expense_correction_operations')
TRIGGERS = [f'{table}_{action}' for table in TABLES for action in ('update','delete')] + ['void_expense_payment_update','void_expense_payment_delete','void_expense_update','void_expense_delete','expense_payment_valid_parent','expense_reversal_valid_parent']

def columns():
    return [sa.Column('request_key',sa.String(36),primary_key=True),
        sa.Column('expense_id',sa.Integer(),sa.ForeignKey('expenses.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('reason',sa.Text(),nullable=False),sa.Column('before_state',sa.JSON(),nullable=False),
        sa.Column('after_state',sa.JSON(),nullable=False),sa.Column('impact',sa.JSON(),nullable=False),
        sa.Column('fingerprint',sa.String(64),nullable=False),sa.Column('reviewed_state',sa.String(64),nullable=False),
        sa.Column('created_at',sa.DateTime(),nullable=False,server_default=sa.func.current_timestamp())]

def upgrade():
    op.add_column('expense_payments',sa.Column('lifecycle',sa.String(12),sa.CheckConstraint("lifecycle IN ('posted','void')",name='ck_expense_payment_lifecycle'),nullable=False,server_default='posted'))
    op.add_column('expense_payments',sa.Column('voided_at',sa.DateTime(),nullable=True))
    op.add_column('expenses',sa.Column('voided_at',sa.DateTime(),nullable=True))
    # Preserve immutable cash facts; permit only the new administrative void transition.
    op.execute('DROP TRIGGER IF EXISTS expense_payments_immutable_update')
    immutable = ('id','expense_id','effective_date','amount','direction','paid_by','paid_by_owner_id','method','reference','notes','corrects_id','request_key','fingerprint','created_at')
    unchanged = ' AND '.join(f'NEW.{field} IS OLD.{field}' for field in immutable)
    op.execute(f"CREATE TRIGGER expense_payments_immutable_update BEFORE UPDATE ON expense_payments WHEN NOT (OLD.lifecycle='posted' AND NEW.lifecycle='void' AND OLD.voided_at IS NULL AND NEW.voided_at IS NOT NULL AND {unchanged}) BEGIN SELECT RAISE(ABORT,'Financial history is immutable'); END")
    op.create_table(TABLES[0],*columns(),
        sa.Column('payment_id',sa.Integer(),sa.ForeignKey('expense_payments.id',ondelete='RESTRICT'),nullable=False,unique=True),
        sa.Column('no_money_moved',sa.Boolean(),nullable=False),
        sa.CheckConstraint('no_money_moved = 1',name='ck_expense_void_no_money'),
        sa.CheckConstraint('length(trim(reason)) > 0',name='ck_expense_payment_void_reason'))
    op.create_table(TABLES[1],*columns(),sa.Column('kind',sa.String(12),nullable=False),
        sa.CheckConstraint("kind IN ('correct','void')",name='ck_expense_correction_kind'),
        sa.CheckConstraint('length(trim(reason)) > 0',name='ck_expense_correction_reason'))
    for table in TABLES:
        op.create_index('ix_'+table+'_expense_id',table,['expense_id'])
        for action in ('update','delete'):
            op.execute(f"CREATE TRIGGER {table}_{action} BEFORE {action.upper()} ON {table} BEGIN SELECT RAISE(ABORT,'expense_audit_immutable'); END")
    for table,prefix in [('expense_payments','void_expense_payment'),('expenses','void_expense')]:
        for action in ('update','delete'):
            op.execute(f"CREATE TRIGGER {prefix}_{action} BEFORE {action.upper()} ON {table} WHEN OLD.lifecycle='void' BEGIN SELECT RAISE(ABORT,'void_expense_movement_immutable'); END")
    op.execute("""CREATE TRIGGER expense_payment_valid_parent BEFORE INSERT ON expense_payments
        WHEN NOT EXISTS(SELECT 1 FROM expenses WHERE id=NEW.expense_id AND lifecycle='posted')
        BEGIN SELECT RAISE(ABORT,'expense_not_active'); END""")
    op.execute("""CREATE TRIGGER expense_reversal_valid_parent BEFORE INSERT ON expense_payments
        WHEN NEW.direction='reversal' AND NOT EXISTS(SELECT 1 FROM expense_payments WHERE id=NEW.corrects_id AND expense_id=NEW.expense_id AND lifecycle='posted' AND direction='payment')
        BEGIN SELECT RAISE(ABORT,'expense_payment_not_active'); END""")

def downgrade():
    db=op.get_bind()
    if any(db.execute(sa.text('select count(*) from '+table)).scalar() for table in TABLES) or db.execute(sa.text("select count(*) from expense_payments where lifecycle!='posted'")).scalar():
        raise RuntimeError('No se elimina historial ni estados de anulaciones existentes.')
    for trigger in TRIGGERS:op.execute('DROP TRIGGER '+trigger)
    for table in TABLES:op.drop_table(table)
    op.execute('DROP TRIGGER expense_payments_immutable_update')
    op.execute("CREATE TRIGGER expense_payments_immutable_update BEFORE UPDATE ON expense_payments BEGIN SELECT RAISE(ABORT,'Financial history is immutable'); END")
    op.drop_column('expenses','voided_at')
    op.drop_column('expense_payments','voided_at')
    op.drop_column('expense_payments','lifecycle')
