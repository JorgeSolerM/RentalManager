"""Add Property rules and reusable rental requirements.

Revision ID: a2c4e6f8b013
Revises: f9b1d3e5a640
"""

import sqlalchemy as sa
from alembic import op


revision = "a2c4e6f8b013"
down_revision = "f9b1d3e5a640"
branch_labels = None
depends_on = None


REQUIREMENTS = (
    ("identity-document", "Documento de identidad", 10),
    ("study-enrollment-proof", "Justificante de estudios o matrícula", 20),
    ("employment-proof", "Contrato de trabajo o justificante laboral", 30),
    ("income-proof", "Justificante de ingresos", 40),
    ("guarantor", "Avalista o garante", 50),
)


def upgrade() -> None:
    op.add_column("properties", sa.Column("smoking_allowed", sa.Boolean(), nullable=True))
    op.add_column("properties", sa.Column("pets_allowed", sa.Boolean(), nullable=True))
    op.add_column("properties", sa.Column("couples_allowed", sa.Boolean(), nullable=True))
    op.add_column(
        "properties",
        sa.Column("musical_instruments_allowed", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "properties",
        sa.Column(
            "minimum_tenant_age",
            sa.Integer(),
            sa.CheckConstraint(
                "minimum_tenant_age IS NULL OR minimum_tenant_age >= 0",
                name="ck_properties_minimum_tenant_age_nonnegative",
            ),
            nullable=True,
        ),
    )
    op.add_column(
        "properties",
        sa.Column(
            "maximum_tenant_age",
            sa.Integer(),
            sa.CheckConstraint(
                "maximum_tenant_age IS NULL OR maximum_tenant_age >= 0",
                name="ck_properties_maximum_tenant_age_nonnegative",
            ),
            sa.CheckConstraint(
                "minimum_tenant_age IS NULL OR maximum_tenant_age IS NULL "
                "OR minimum_tenant_age <= maximum_tenant_age",
                name="ck_properties_tenant_age_range",
            ),
            nullable=True,
        ),
    )

    op.create_table(
        "rental_requirements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("public_name", sa.String(140), nullable=False),
        sa.Column("public_description", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.CheckConstraint(
            "display_order >= 0",
            name="ck_rental_requirements_display_order_nonnegative",
        ),
        sa.UniqueConstraint("slug", name="uq_rental_requirements_slug"),
    )
    op.create_table(
        "property_requirements",
        sa.Column("property_id", sa.Integer(), nullable=False),
        sa.Column("requirement_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["property_id"], ["properties.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["requirement_id"], ["rental_requirements.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("property_id", "requirement_id"),
    )
    op.create_index(
        "ix_property_requirements_requirement_id",
        "property_requirements",
        ["requirement_id"],
    )

    for slug, name, order in REQUIREMENTS:
        escaped_slug = slug.replace("'", "''")
        escaped_name = name.replace("'", "''")
        op.execute(
            "INSERT OR IGNORE INTO rental_requirements "
            "(slug, public_name, public_description, active, display_order) "
            f"VALUES ('{escaped_slug}', '{escaped_name}', NULL, 1, {order})"
        )


def downgrade() -> None:
    op.drop_index(
        "ix_property_requirements_requirement_id",
        table_name="property_requirements",
    )
    op.drop_table("property_requirements")
    op.drop_table("rental_requirements")
    op.drop_column("properties", "maximum_tenant_age")
    op.drop_column("properties", "minimum_tenant_age")
    op.drop_column("properties", "musical_instruments_allowed")
    op.drop_column("properties", "couples_allowed")
    op.drop_column("properties", "pets_allowed")
    op.drop_column("properties", "smoking_allowed")
