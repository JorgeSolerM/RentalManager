"""Add people and their explicit roles in bookings.

Revision ID: a3c5e7f9b126
Revises: f2d4b6c8a014
"""
from alembic import op
import sqlalchemy as sa


revision = "a3c5e7f9b126"
down_revision = "f2d4b6c8a014"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "persons",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("full_name", sa.String(160), nullable=False),
        sa.Column("display_name", sa.String(160)),
        sa.Column("phone", sa.String(40)),
        sa.Column("email", sa.String(254)),
        sa.Column("document_type", sa.String(20)),
        sa.Column("document_number", sa.String(60)),
        sa.Column("document_issuer_country", sa.String(2)),
        sa.Column("birth_date", sa.Date()),
        sa.Column("nationality", sa.String(2)),
        sa.Column("address_line", sa.String(255)),
        sa.Column("postal_code", sa.String(20)),
        sa.Column("city", sa.String(120)),
        sa.Column("province", sa.String(120)),
        sa.Column("country", sa.String(2)),
        sa.Column("notes", sa.Text()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("verification_status", sa.String(20), nullable=False, server_default="unverified"),
        sa.Column("source", sa.String(20), nullable=False, server_default="manual"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.CheckConstraint("length(trim(full_name)) > 0", name="ck_persons_full_name_not_blank"),
        sa.CheckConstraint("document_type IS NULL OR document_type IN ('dni','nie','passport','other')", name="ck_persons_document_type"),
        sa.CheckConstraint("verification_status IN ('unverified','verified')", name="ck_persons_verification_status"),
        sa.CheckConstraint("source IN ('manual','legacy_guest')", name="ck_persons_source"),
        sa.CheckConstraint("document_issuer_country IS NULL OR (length(document_issuer_country) = 2 AND document_issuer_country = upper(document_issuer_country))", name="ck_persons_document_issuer_country"),
        sa.CheckConstraint("nationality IS NULL OR (length(nationality) = 2 AND nationality = upper(nationality))", name="ck_persons_nationality"),
        sa.CheckConstraint("country IS NULL OR (length(country) = 2 AND country = upper(country))", name="ck_persons_country"),
    )
    op.add_column("bookings", sa.Column("source_guest_name", sa.String(160), nullable=True))
    op.create_table(
        "booking_parties",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("booking_id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["person_id"], ["persons.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("booking_id", "person_id", "role", name="uq_booking_parties_booking_person_role"),
        sa.CheckConstraint("role IN ('tenant','occupant','payer','guarantor','unclassified')", name="ck_booking_parties_role"),
    )
    op.create_index("ix_booking_parties_booking_id", "booking_parties", ["booking_id"])
    op.create_index("ix_booking_parties_person_id", "booking_parties", ["person_id"])

    # Preserve identity and spelling exactly. Guest IDs are retained as Person
    # IDs to keep an explicit, inspectable transition correspondence.
    op.execute(sa.text(
        "INSERT INTO persons (id,full_name,display_name,phone,email,notes,active,verification_status,source) "
        "SELECT id,full_name,display_name,phone,email,notes,active,'unverified','legacy_guest' FROM guests"
    ))
    op.execute(sa.text(
        "UPDATE bookings SET source_guest_name=(SELECT full_name FROM guests WHERE guests.id=bookings.guest_id) "
        "WHERE guest_id IS NOT NULL"
    ))
    op.execute(sa.text(
        "INSERT INTO booking_parties (booking_id,person_id,role) "
        "SELECT id,guest_id,'unclassified' FROM bookings WHERE guest_id IS NOT NULL"
    ))


def downgrade():
    op.drop_table("booking_parties")
    op.drop_column("bookings", "source_guest_name")
    op.drop_table("persons")
