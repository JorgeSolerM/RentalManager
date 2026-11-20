"""Append-only payout administrative corrections; economic branch only."""
from alembic import op
import sqlalchemy as sa
revision='067d8f3249ae'
down_revision='f56c7e21389d'
branch_labels=None
depends_on=None
TABLE='owner_payout_correction_operations'

def upgrade():
    op.create_table(TABLE,
        sa.Column('request_key',sa.String(36),primary_key=True),
        sa.Column('original_payout_id',sa.Integer(),sa.ForeignKey('owner_payouts.id',ondelete='RESTRICT'),nullable=False,unique=True),
        sa.Column('replacement_payout_id',sa.Integer(),sa.ForeignKey('owner_payouts.id',ondelete='RESTRICT'),nullable=True,unique=True),
        sa.Column('kind',sa.String(12),nullable=False),sa.Column('reason',sa.Text(),nullable=False),
        sa.Column('no_transfer',sa.Boolean(),nullable=False),sa.Column('operator_id',sa.String(160),nullable=True),
        sa.Column('created_at',sa.DateTime(),nullable=False,server_default=sa.func.current_timestamp()),
        sa.Column('before_state',sa.JSON(),nullable=False),sa.Column('after_state',sa.JSON(),nullable=False),sa.Column('impact',sa.JSON(),nullable=False),
        sa.Column('fingerprint',sa.String(64),nullable=False),sa.Column('reviewed_state',sa.String(64),nullable=False),
        sa.CheckConstraint("kind IN ('void','replace')",name='ck_payout_correction_kind'),
        sa.CheckConstraint("(kind='void' AND replacement_payout_id IS NULL AND no_transfer=1) OR (kind='replace' AND replacement_payout_id IS NOT NULL AND no_transfer=0)",name='ck_payout_correction_shape'),
        sa.CheckConstraint('original_payout_id != replacement_payout_id',name='ck_payout_correction_distinct'),
        sa.CheckConstraint('length(trim(reason))>0',name='ck_payout_correction_reason'))
    for action in ('update','delete'):
        op.execute(f"CREATE TRIGGER payout_correction_no_{action} BEFORE {action.upper()} ON {TABLE} BEGIN SELECT RAISE(ABORT,'payout_correction_immutable'); END")
    op.execute(f"""CREATE TRIGGER payout_correction_same_destination BEFORE INSERT ON {TABLE}
        WHEN NEW.kind='replace' AND NOT EXISTS (
            SELECT 1 FROM owner_payouts a JOIN owner_payouts b ON b.id=NEW.replacement_payout_id
            WHERE a.id=NEW.original_payout_id AND b.id>a.id AND a.owner_id=b.owner_id
            AND a.settlement_id=b.settlement_id AND a.bank_account_id=b.bank_account_id
            AND a.account_snapshot=b.account_snapshot AND a.method=b.method)
        BEGIN SELECT RAISE(ABORT,'payout_destination_immutable'); END""")

def downgrade():
    if op.get_bind().execute(sa.text('select count(*) from '+TABLE)).scalar():raise RuntimeError('No eliminar historial de correcciones existente.')
    for name in ('payout_correction_no_update','payout_correction_no_delete','payout_correction_same_destination'):op.execute('DROP TRIGGER '+name)
    op.drop_table(TABLE)
