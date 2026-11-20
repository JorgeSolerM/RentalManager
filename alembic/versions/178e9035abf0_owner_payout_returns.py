"""Confirmed bank returns, additive economic branch."""
from alembic import op
import sqlalchemy as sa
revision='178e9035abf0'
down_revision='067d8f3249ae'
branch_labels=None
depends_on=None
TABLE='owner_payout_returns'
TRIGGERS=('payout_return_no_update','payout_return_no_delete','payout_return_valid_source','payout_correction_no_received_returns')

def upgrade():
    op.create_table(TABLE,
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('payout_id',sa.Integer(),sa.ForeignKey('owner_payouts.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('transfer_root_id',sa.Integer(),sa.ForeignKey('owner_payouts.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('amount',sa.Numeric(12,2),nullable=False),sa.Column('effective_date',sa.Date(),nullable=False),
        sa.Column('bank_reference',sa.String(255),nullable=False),sa.Column('bank_transaction_id',sa.String(160),nullable=True),
        sa.Column('receiving_account_hash',sa.String(64),nullable=False),sa.Column('receiving_account_suffix',sa.String(4),nullable=False),
        sa.Column('reason',sa.Text(),nullable=False),sa.Column('received',sa.Boolean(),nullable=False),sa.Column('operator_id',sa.String(160),nullable=True),
        sa.Column('created_at',sa.DateTime(),nullable=False,server_default=sa.func.current_timestamp()),
        sa.Column('request_key',sa.String(36),nullable=False,unique=True),sa.Column('dedupe_key',sa.String(64),nullable=False,unique=True),
        sa.Column('fingerprint',sa.String(64),nullable=False),sa.Column('reviewed_state',sa.String(64),nullable=False),sa.Column('impact',sa.JSON(),nullable=False),
        sa.CheckConstraint('amount>0',name='ck_payout_return_amount'),sa.CheckConstraint('received=1',name='ck_payout_return_received'),sa.CheckConstraint('length(trim(reason))>0 AND length(trim(bank_reference))>0',name='ck_payout_return_evidence'))
    for field in ('payout_id','transfer_root_id'):op.create_index('ix_owner_payout_returns_'+field,TABLE,[field])
    for action in ('update','delete'):op.execute(f"CREATE TRIGGER payout_return_no_{action} BEFORE {action.upper()} ON {TABLE} BEGIN SELECT RAISE(ABORT,'payout_return_immutable'); END")
    op.execute("""CREATE TRIGGER payout_return_valid_source BEFORE INSERT ON owner_payout_returns
        WHEN NOT EXISTS(SELECT 1 FROM owner_payouts p JOIN owner_payouts root ON root.id=NEW.transfer_root_id
            WHERE p.id=NEW.payout_id AND p.owner_id=root.owner_id AND p.settlement_id=root.settlement_id
            AND root.id=(WITH RECURSIVE ancestors(id) AS (
                SELECT p.id UNION ALL SELECT o.original_payout_id FROM owner_payout_correction_operations o JOIN ancestors a ON o.replacement_payout_id=a.id
            ) SELECT id FROM ancestors WHERE NOT EXISTS(SELECT 1 FROM owner_payout_correction_operations o WHERE o.replacement_payout_id=ancestors.id))
            AND NEW.effective_date>=p.effective_date AND p.method='bank_transfer'
            AND NOT EXISTS(SELECT 1 FROM owner_payout_correction_operations o WHERE o.original_payout_id=p.id)
            AND ROUND(NEW.amount + COALESCE((SELECT SUM(r.amount) FROM owner_payout_returns r WHERE r.transfer_root_id=NEW.transfer_root_id),0),2)<=ROUND(p.amount,2))
        BEGIN SELECT RAISE(ABORT,'invalid_payout_return'); END""")
    op.execute("""CREATE TRIGGER payout_correction_no_received_returns BEFORE INSERT ON owner_payout_correction_operations
        WHEN EXISTS(SELECT 1 FROM owner_payout_returns WHERE payout_id=NEW.original_payout_id)
        BEGIN SELECT RAISE(ABORT,'payout_has_received_returns'); END""")

def downgrade():
    if op.get_bind().execute(sa.text('select count(*) from '+TABLE)).scalar():raise RuntimeError('No eliminar devoluciones históricas.')
    for trigger in TRIGGERS:op.execute('DROP TRIGGER '+trigger)
    op.drop_table(TABLE)
