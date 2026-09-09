"""Add SEPA creditor profiles, mandates and booking links.

Revision ID: d6f8a0b2c459
Revises: c5e7a9b1d348
"""
from alembic import op
import sqlalchemy as sa


revision = "d6f8a0b2c459"
down_revision = "c5e7a9b1d348"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "sepa_creditor_profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("display_name", sa.String(180), nullable=False),
        sa.Column("creditor_name", sa.String(180), nullable=False),
        sa.Column("creditor_identifier", sa.String(35), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=True),
        sa.Column("bank_account_id", sa.Integer(), nullable=False),
        sa.Column("scheme", sa.String(10), server_default="CORE", nullable=False),
        sa.Column("active", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.CheckConstraint("scheme IN ('CORE')", name="ck_sepa_creditor_profiles_scheme"),
        sa.ForeignKeyConstraint(["owner_id"], ["owners.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["bank_account_id"], ["owner_bank_accounts.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sepa_creditor_profiles_owner_id", "sepa_creditor_profiles", ["owner_id"])
    op.create_index("ix_sepa_creditor_profiles_bank_account_id", "sepa_creditor_profiles", ["bank_account_id"])
    op.create_index("uq_sepa_creditor_profiles_active_account", "sepa_creditor_profiles", ["bank_account_id"], unique=True, sqlite_where=sa.text("active = 1"))
    op.create_table(
        "sepa_mandates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("creditor_profile_id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=True),
        sa.Column("debtor_name", sa.String(180), nullable=False),
        sa.Column("debtor_iban", sa.String(34), nullable=False),
        sa.Column("debtor_bic", sa.String(11), nullable=True),
        sa.Column("mandate_reference", sa.String(35), nullable=False),
        sa.Column("signature_date", sa.Date(), nullable=False),
        sa.Column("mandate_type", sa.String(10), server_default="RCUR", nullable=False),
        sa.Column("status", sa.String(20), server_default="draft", nullable=False),
        sa.Column("amendment_indicator", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("active_from", sa.Date(), nullable=True),
        sa.Column("cancelled_at", sa.Date(), nullable=True),
        sa.Column("last_used_at", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.CheckConstraint("mandate_type IN ('RCUR','OOFF')", name="ck_sepa_mandates_type"),
        sa.CheckConstraint("status IN ('draft','active','cancelled','expired')", name="ck_sepa_mandates_status"),
        sa.ForeignKeyConstraint(["creditor_profile_id"], ["sepa_creditor_profiles.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["person_id"], ["persons.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("creditor_profile_id", "mandate_reference", name="uq_sepa_mandates_creditor_reference"),
    )
    op.create_index("ix_sepa_mandates_creditor_profile_id", "sepa_mandates", ["creditor_profile_id"])
    op.create_index("ix_sepa_mandates_person_id", "sepa_mandates", ["person_id"])
    op.create_table(
        "booking_sepa_mandates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("booking_id", sa.Integer(), nullable=False),
        sa.Column("mandate_id", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["mandate_id"], ["sepa_mandates.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("booking_id", "mandate_id", name="uq_booking_sepa_mandates_booking_mandate"),
    )
    op.create_index("ix_booking_sepa_mandates_booking_id", "booking_sepa_mandates", ["booking_id"])
    op.create_index("ix_booking_sepa_mandates_mandate_id", "booking_sepa_mandates", ["mandate_id"])
    op.create_index("uq_booking_sepa_mandates_active_booking", "booking_sepa_mandates", ["booking_id"], unique=True, sqlite_where=sa.text("active = 1"))


def downgrade():
    op.drop_index("uq_booking_sepa_mandates_active_booking", table_name="booking_sepa_mandates")
    op.drop_index("ix_booking_sepa_mandates_mandate_id", table_name="booking_sepa_mandates")
    op.drop_index("ix_booking_sepa_mandates_booking_id", table_name="booking_sepa_mandates")
    op.drop_table("booking_sepa_mandates")
    op.drop_index("ix_sepa_mandates_person_id", table_name="sepa_mandates")
    op.drop_index("ix_sepa_mandates_creditor_profile_id", table_name="sepa_mandates")
    op.drop_table("sepa_mandates")
    op.drop_index("uq_sepa_creditor_profiles_active_account", table_name="sepa_creditor_profiles")
    op.drop_index("ix_sepa_creditor_profiles_bank_account_id", table_name="sepa_creditor_profiles")
    op.drop_index("ix_sepa_creditor_profiles_owner_id", table_name="sepa_creditor_profiles")
    op.drop_table("sepa_creditor_profiles")
