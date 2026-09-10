from alembic import op
import sqlalchemy as sa

revision = "f8b0d2e4a671"
down_revision = "e7a9b1c3d560"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('sepa_batches',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('reference', sa.String(length=35), nullable=False),
    sa.Column('request_key', sa.String(length=36), nullable=False),
    sa.Column('period', sa.Date(), nullable=False),
    sa.Column('requested_collection_date', sa.Date(), nullable=False),
    sa.Column('status', sa.String(length=30), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
    sa.Column('exported_at', sa.DateTime(), nullable=True),
    sa.Column('presented_at', sa.DateTime(), nullable=True),
    sa.CheckConstraint("status IN ('prepared','exported','presented','partially_collected','collected')", name='ck_sepa_batches_status'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('reference'),
    sa.UniqueConstraint('request_key')
    )
    op.create_table('sepa_settings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('initiator_name', sa.String(length=70), nullable=True),
    sa.Column('initiator_identifier', sa.String(length=35), nullable=True),
    sa.CheckConstraint('id = 1', name='ck_sepa_settings_singleton'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('sepa_batch_groups',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('batch_id', sa.Integer(), nullable=False),
    sa.Column('creditor_profile_id', sa.Integer(), nullable=False),
    sa.Column('bank_account_id', sa.Integer(), nullable=False),
    sa.Column('snapshot', sa.JSON(), nullable=False),
    sa.ForeignKeyConstraint(['bank_account_id'], ['owner_bank_accounts.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['batch_id'], ['sepa_batches.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['creditor_profile_id'], ['sepa_creditor_profiles.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('batch_id', 'creditor_profile_id', name='uq_sepa_group_creditor')
    )
    op.create_index(op.f('ix_sepa_batch_groups_batch_id'), 'sepa_batch_groups', ['batch_id'], unique=False)
    op.create_table('sepa_export_artifacts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('group_id', sa.Integer(), nullable=False),
    sa.Column('filename', sa.String(length=100), nullable=False),
    sa.Column('sha256', sa.String(length=64), nullable=False),
    sa.Column('format', sa.String(length=40), nullable=False),
    sa.Column('generated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
    sa.Column('transaction_count', sa.Integer(), nullable=False),
    sa.Column('control_sum', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.CheckConstraint('transaction_count > 0 AND control_sum > 0', name='ck_sepa_artifact_totals'),
    sa.ForeignKeyConstraint(['group_id'], ['sepa_batch_groups.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('filename'),
    sa.UniqueConstraint('group_id')
    )
    op.create_table('sepa_debits',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('group_id', sa.Integer(), nullable=False),
    sa.Column('booking_id', sa.Integer(), nullable=False),
    sa.Column('mandate_id', sa.Integer(), nullable=False),
    sa.Column('creditor_profile_id', sa.Integer(), nullable=False),
    sa.Column('payment_id', sa.Integer(), nullable=True),
    sa.Column('retry_of_id', sa.Integer(), nullable=True),
    sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('requested_collection_date', sa.Date(), nullable=False),
    sa.Column('end_to_end_id', sa.String(length=35), nullable=False),
    sa.Column('remittance_information', sa.String(length=140), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('snapshot', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
    sa.Column('collected_at', sa.DateTime(), nullable=True),
    sa.CheckConstraint("(status = 'collected' AND payment_id IS NOT NULL AND collected_at IS NOT NULL) OR (status != 'collected' AND payment_id IS NULL AND collected_at IS NULL)", name='ck_sepa_debit_collection'),
    sa.CheckConstraint("amount > 0 AND currency = 'EUR'", name='ck_sepa_debit_money'),
    sa.CheckConstraint("status IN ('prepared','presented','collected')", name='ck_sepa_debit_status'),
    sa.ForeignKeyConstraint(['booking_id'], ['bookings.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['creditor_profile_id'], ['sepa_creditor_profiles.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['group_id'], ['sepa_batch_groups.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['mandate_id'], ['sepa_mandates.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['payment_id'], ['payments.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['retry_of_id'], ['sepa_debits.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('end_to_end_id'),
    sa.UniqueConstraint('group_id', 'booking_id', 'mandate_id', name='uq_sepa_debit_booking'),
    sa.UniqueConstraint('payment_id')
    )
    op.create_index(op.f('ix_sepa_debits_booking_id'), 'sepa_debits', ['booking_id'], unique=False)
    op.create_index(op.f('ix_sepa_debits_group_id'), 'sepa_debits', ['group_id'], unique=False)
    op.create_table('sepa_debit_charge_allocations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('debit_id', sa.Integer(), nullable=False),
    sa.Column('charge_id', sa.Integer(), nullable=False),
    sa.Column('reserved', sa.Boolean(), server_default='1', nullable=False),
    sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.CheckConstraint('amount > 0', name='ck_sepa_debit_allocation_amount'),
    sa.ForeignKeyConstraint(['charge_id'], ['booking_charges.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['debit_id'], ['sepa_debits.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('debit_id', 'charge_id', name='uq_sepa_debit_charge')
    )
    op.create_index(op.f('ix_sepa_debit_charge_allocations_debit_id'), 'sepa_debit_charge_allocations', ['debit_id'], unique=False)
    op.create_index('uq_sepa_charge_reservation', 'sepa_debit_charge_allocations', ['charge_id'], unique=True, sqlite_where=sa.text('reserved = 1'))


def downgrade():
    op.drop_index('uq_sepa_charge_reservation', table_name='sepa_debit_charge_allocations')
    op.drop_index(op.f('ix_sepa_debit_charge_allocations_debit_id'), table_name='sepa_debit_charge_allocations')
    op.drop_table('sepa_debit_charge_allocations')
    op.drop_index(op.f('ix_sepa_debits_group_id'), table_name='sepa_debits')
    op.drop_index(op.f('ix_sepa_debits_booking_id'), table_name='sepa_debits')
    op.drop_table('sepa_debits')
    op.drop_table('sepa_export_artifacts')
    op.drop_index(op.f('ix_sepa_batch_groups_batch_id'), table_name='sepa_batch_groups')
    op.drop_table('sepa_batch_groups')
    op.drop_table('sepa_settings')
    op.drop_table('sepa_batches')
