"""Administrative early departure history; no backfill or ledger mutation."""
from alembic import op
import sqlalchemy as sa

revision = 'b1283aedf459'
# This previously uncommitted revision is published independently of billing.
# Existing databases already at b1283aedf459 require no stamp or data changes.
down_revision = 'fe0618cad237'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('booking_early_terminations',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('booking_id', sa.Integer(), sa.ForeignKey('bookings.id', ondelete='RESTRICT'), nullable=False, unique=True),
        sa.Column('request_key', sa.String(36), nullable=False, unique=True),
        sa.Column('original_check_in', sa.Date(), nullable=False),
        sa.Column('original_check_out', sa.Date(), nullable=False),
        sa.Column('effective_departure', sa.Date(), nullable=False),
        sa.Column('economic_last_day', sa.Date(), nullable=False),
        sa.Column('reason', sa.String(500)), sa.Column('notes', sa.Text()), sa.Column('actor', sa.String(160)),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column('snapshot', sa.JSON(), nullable=False),
        sa.CheckConstraint('effective_departure > original_check_in AND effective_departure < original_check_out', name='ck_early_departure_interval'),
        sa.CheckConstraint('economic_last_day >= original_check_in AND economic_last_day < original_check_out', name='ck_early_economic_interval'))
    op.create_table('booking_early_termination_source_states',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('termination_id', sa.Integer(), sa.ForeignKey('booking_early_terminations.id', ondelete='RESTRICT'), nullable=False, unique=True),
        sa.Column('source_check_in', sa.Date(), nullable=False), sa.Column('source_check_out', sa.Date(), nullable=False),
        sa.Column('seen_at', sa.DateTime(), nullable=False))
    for action in ('UPDATE', 'DELETE'):
        op.execute(f"CREATE TRIGGER early_termination_immutable_{action.lower()} BEFORE {action} ON booking_early_terminations BEGIN SELECT RAISE(ABORT, 'Early termination history is immutable'); END")
    op.execute("CREATE TRIGGER early_termination_dates_guard BEFORE UPDATE OF check_in, check_out, expected_departure_date ON bookings WHEN EXISTS (SELECT 1 FROM booking_early_terminations t WHERE t.booking_id=OLD.id AND (NEW.check_in!=t.original_check_in OR NEW.check_out!=t.effective_departure OR (NEW.expected_departure_date IS NOT NULL AND NEW.expected_departure_date!=t.effective_departure))) BEGIN SELECT RAISE(ABORT, 'Early termination dates are protected'); END")


def downgrade():
    for table in ('booking_early_terminations', 'booking_early_termination_source_states'):
        if op.get_bind().execute(sa.text(f'SELECT COUNT(*) FROM {table}')).scalar():
            raise RuntimeError('Downgrade bloqueado: debe conservarse el historial de salidas anticipadas.')
    op.execute('DROP TRIGGER early_termination_dates_guard')
    op.drop_table('booking_early_termination_source_states')
    op.drop_table('booking_early_terminations')
