"""Add owners, bank accounts and property ownerships.

Revision ID: c5e7a9b1d348
Revises: b4d6f8a0c237
"""
from alembic import op
import sqlalchemy as sa


revision = "c5e7a9b1d348"
down_revision = "b4d6f8a0c237"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "owners",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("legal_name", sa.String(180), nullable=False),
        sa.Column("display_name", sa.String(180), nullable=True),
        sa.Column("tax_id", sa.String(40), nullable=True),
        sa.Column("email", sa.String(254), nullable=True),
        sa.Column("phone", sa.String(40), nullable=True),
        sa.Column("address_line", sa.String(255), nullable=True),
        sa.Column("postal_code", sa.String(20), nullable=True),
        sa.Column("city", sa.String(120), nullable=True),
        sa.Column("province", sa.String(120), nullable=True),
        sa.Column("country", sa.String(2), nullable=True),
        sa.Column("active", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.CheckConstraint("length(trim(legal_name)) > 0", name="ck_owners_legal_name_not_blank"),
        sa.CheckConstraint("country IS NULL OR (length(country) = 2 AND country = upper(country))", name="ck_owners_country"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "owner_bank_accounts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("account_holder_name", sa.String(180), nullable=False),
        sa.Column("iban", sa.String(34), nullable=False),
        sa.Column("bic", sa.String(11), nullable=True),
        sa.Column("alias", sa.String(100), nullable=True),
        sa.Column("currency", sa.String(3), server_default="EUR", nullable=False),
        sa.Column("active", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("receives_rent", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("receives_settlements", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.CheckConstraint("length(trim(account_holder_name)) > 0", name="ck_owner_bank_accounts_holder_not_blank"),
        sa.CheckConstraint("length(currency) = 3 AND currency = upper(currency)", name="ck_owner_bank_accounts_currency"),
        sa.ForeignKeyConstraint(["owner_id"], ["owners.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id", "iban", name="uq_owner_bank_accounts_owner_iban"),
    )
    op.create_index("ix_owner_bank_accounts_owner_id", "owner_bank_accounts", ["owner_id"])
    op.create_table(
        "property_ownerships",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("property_id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("ownership_percentage", sa.Numeric(5, 2), nullable=False),
        sa.Column("rent_bank_account_id", sa.Integer(), nullable=True),
        sa.Column("active", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_until", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.CheckConstraint("ownership_percentage > 0 AND ownership_percentage <= 100", name="ck_property_ownerships_percentage"),
        sa.CheckConstraint("effective_until IS NULL OR effective_from IS NULL OR effective_until >= effective_from", name="ck_property_ownerships_effective_range"),
        sa.ForeignKeyConstraint(["owner_id"], ["owners.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["rent_bank_account_id"], ["owner_bank_accounts.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_property_ownerships_owner_id", "property_ownerships", ["owner_id"])
    op.create_index("ix_property_ownerships_property_id", "property_ownerships", ["property_id"])
    op.create_index("ix_property_ownerships_rent_bank_account_id", "property_ownerships", ["rent_bank_account_id"])
    op.create_index(
        "uq_property_ownerships_active_owner",
        "property_ownerships",
        ["property_id", "owner_id"],
        unique=True,
        sqlite_where=sa.text("active = 1"),
    )


def downgrade():
    op.drop_index("uq_property_ownerships_active_owner", table_name="property_ownerships")
    op.drop_index("ix_property_ownerships_rent_bank_account_id", table_name="property_ownerships")
    op.drop_index("ix_property_ownerships_property_id", table_name="property_ownerships")
    op.drop_index("ix_property_ownerships_owner_id", table_name="property_ownerships")
    op.drop_table("property_ownerships")
    op.drop_index("ix_owner_bank_accounts_owner_id", table_name="owner_bank_accounts")
    op.drop_table("owner_bank_accounts")
    op.drop_table("owners")
