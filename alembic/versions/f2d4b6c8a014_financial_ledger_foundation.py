"""financial ledger foundation

Revision ID: f2d4b6c8a014
Revises: e1c3a5b7d902
"""
from alembic import op
import sqlalchemy as sa

revision = "f2d4b6c8a014"
down_revision = "e1c3a5b7d902"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("booking_financial_terms",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("booking_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False), sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_until", sa.Date()), sa.Column("monthly_rent", sa.Numeric(12,2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False), sa.Column("usual_due_day", sa.Integer(), nullable=False),
        sa.Column("deposit_agreed", sa.Numeric(12,2), nullable=False), sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("confirmed_at", sa.DateTime()), sa.Column("supersedes_id", sa.Integer()), sa.Column("notes", sa.Text()),
        sa.ForeignKeyConstraint(["booking_id"],["bookings.id"],ondelete="RESTRICT"),
        sa.UniqueConstraint("booking_id","version",name="uq_booking_financial_terms_version"),
        sa.CheckConstraint("version > 0",name="ck_booking_financial_terms_version_positive"),
        sa.CheckConstraint("monthly_rent >= 0",name="ck_booking_financial_terms_rent_nonnegative"),
        sa.CheckConstraint("deposit_agreed >= 0",name="ck_booking_financial_terms_deposit_nonnegative"),
        sa.CheckConstraint("usual_due_day BETWEEN 1 AND 31",name="ck_booking_financial_terms_due_day"),
        sa.CheckConstraint("length(currency) = 3 AND currency = upper(currency)",name="ck_booking_financial_terms_currency"),
        sa.CheckConstraint("status IN ('draft','confirmed','superseded')",name="ck_booking_financial_terms_status"),
        sa.CheckConstraint("effective_until IS NULL OR effective_until > effective_from",name="ck_booking_financial_terms_period"),
        sa.CheckConstraint("status != 'confirmed' OR confirmed_at IS NOT NULL",name="ck_booking_financial_terms_confirmation"))
    op.create_index("ix_booking_financial_terms_booking_id","booking_financial_terms",["booking_id"])
    op.create_table("booking_charges",
        sa.Column("id",sa.Integer(),primary_key=True),sa.Column("booking_id",sa.Integer(),nullable=False),sa.Column("financial_terms_id",sa.Integer()),
        sa.Column("type",sa.String(30),nullable=False),sa.Column("direction",sa.String(10),nullable=False),sa.Column("concept",sa.String(255),nullable=False),
        sa.Column("service_period_start",sa.Date()),sa.Column("service_period_end",sa.Date()),sa.Column("due_date",sa.Date(),nullable=False),
        sa.Column("amount",sa.Numeric(12,2),nullable=False),sa.Column("currency",sa.String(3),nullable=False),sa.Column("lifecycle",sa.String(10),nullable=False),
        sa.Column("generation_key",sa.String(120)),sa.Column("corrects_charge_id",sa.Integer()),sa.Column("reason",sa.Text()),
        sa.Column("created_at",sa.DateTime(),nullable=False,server_default=sa.func.current_timestamp()),sa.Column("posted_at",sa.DateTime()),sa.Column("voided_at",sa.DateTime()),
        sa.ForeignKeyConstraint(["booking_id"],["bookings.id"],ondelete="RESTRICT"),sa.ForeignKeyConstraint(["financial_terms_id"],["booking_financial_terms.id"],ondelete="RESTRICT"),
        sa.CheckConstraint("type IN ('rent','security_deposit','reservation_deposit','utilities','extraordinary','discount','deposit_retention')",name="ck_booking_charges_type"),
        sa.CheckConstraint("direction IN ('debit','credit')",name="ck_booking_charges_direction"),sa.CheckConstraint("type != 'discount' OR direction = 'credit'",name="ck_booking_charges_discount_credit"),sa.CheckConstraint("type = 'discount' OR direction = 'debit'",name="ck_booking_charges_non_discount_debit"),
        sa.CheckConstraint("amount > 0",name="ck_booking_charges_amount_positive"),sa.CheckConstraint("length(currency) = 3 AND currency = upper(currency)",name="ck_booking_charges_currency"),sa.CheckConstraint("lifecycle IN ('draft','posted','void')",name="ck_booking_charges_lifecycle"),
        sa.CheckConstraint("service_period_end IS NULL OR service_period_start IS NOT NULL",name="ck_booking_charges_period_start"),sa.CheckConstraint("service_period_end IS NULL OR service_period_end > service_period_start",name="ck_booking_charges_period"),sa.CheckConstraint("lifecycle != 'posted' OR posted_at IS NOT NULL",name="ck_booking_charges_posted"),sa.CheckConstraint("lifecycle != 'void' OR voided_at IS NOT NULL",name="ck_booking_charges_voided"))
    op.create_index("ix_booking_charges_booking_id","booking_charges",["booking_id"]); op.create_index("ix_booking_charges_due_date","booking_charges",["due_date"])
    op.create_index("uq_booking_charges_generation_key","booking_charges",["booking_id","generation_key"],unique=True,sqlite_where=sa.text("generation_key IS NOT NULL"))
    op.create_table("payments",
        sa.Column("id",sa.Integer(),primary_key=True),sa.Column("booking_id",sa.Integer(),nullable=False),sa.Column("effective_date",sa.Date(),nullable=False),sa.Column("amount",sa.Numeric(12,2),nullable=False),sa.Column("currency",sa.String(3),nullable=False),sa.Column("direction",sa.String(10),nullable=False),sa.Column("method",sa.String(30),nullable=False),sa.Column("external_reference",sa.String(255)),sa.Column("lifecycle",sa.String(10),nullable=False),sa.Column("corrects_payment_id",sa.Integer()),sa.Column("notes",sa.Text()),sa.Column("created_at",sa.DateTime(),nullable=False,server_default=sa.func.current_timestamp()),sa.Column("posted_at",sa.DateTime()),sa.Column("voided_at",sa.DateTime()),
        sa.ForeignKeyConstraint(["booking_id"],["bookings.id"],ondelete="RESTRICT"),
        sa.CheckConstraint("amount > 0",name="ck_payments_amount_positive"),sa.CheckConstraint("length(currency) = 3 AND currency = upper(currency)",name="ck_payments_currency"),sa.CheckConstraint("direction IN ('receipt','refund')",name="ck_payments_direction"),sa.CheckConstraint("method IN ('bank_transfer','cash','card_or_platform','sepa_direct_debit','other')",name="ck_payments_method"),sa.CheckConstraint("lifecycle IN ('draft','posted','void')",name="ck_payments_lifecycle"),sa.CheckConstraint("lifecycle != 'posted' OR posted_at IS NOT NULL",name="ck_payments_posted"),sa.CheckConstraint("lifecycle != 'void' OR voided_at IS NOT NULL",name="ck_payments_voided"))
    op.create_index("ix_payments_booking_id","payments",["booking_id"]); op.create_index("ix_payments_effective_date","payments",["effective_date"])
    op.create_table("payment_allocations",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("payment_id",sa.Integer(),nullable=False),sa.Column("charge_id",sa.Integer(),nullable=False),sa.Column("amount",sa.Numeric(12,2),nullable=False),sa.Column("created_at",sa.DateTime(),nullable=False,server_default=sa.func.current_timestamp()),sa.ForeignKeyConstraint(["payment_id"],["payments.id"],ondelete="RESTRICT"),sa.ForeignKeyConstraint(["charge_id"],["booking_charges.id"],ondelete="RESTRICT"),sa.UniqueConstraint("payment_id","charge_id",name="uq_payment_allocations_pair"),sa.CheckConstraint("amount > 0",name="ck_payment_allocations_amount_positive"))
    op.create_index("ix_payment_allocations_payment_id","payment_allocations",["payment_id"]); op.create_index("ix_payment_allocations_charge_id","payment_allocations",["charge_id"])


def downgrade():
    op.drop_table("payment_allocations"); op.drop_table("payments"); op.drop_table("booking_charges"); op.drop_table("booking_financial_terms")
