"""Add the public room listing data foundation.

Revision ID: f6b8d0e2a413
Revises: e3a5c7d9f102
Create Date: 2026-08-20
"""

import sqlalchemy as sa
from alembic import op


revision = "f6b8d0e2a413"
down_revision = "e3a5c7d9f102"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("properties", sa.Column("public_title", sa.String(160), nullable=True))
    op.add_column("properties", sa.Column("public_description", sa.Text(), nullable=True))
    op.add_column("properties", sa.Column("public_location", sa.String(160), nullable=True))
    op.add_column("properties", sa.Column("public_slug", sa.String(180), nullable=True))
    op.add_column(
        "properties",
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default="0"),
    )
    op.create_index(
        "uq_properties_public_slug",
        "properties",
        ["public_slug"],
        unique=True,
        sqlite_where=sa.text("public_slug IS NOT NULL"),
    )

    op.add_column("rooms", sa.Column("public_title", sa.String(160), nullable=True))
    op.add_column("rooms", sa.Column("public_description", sa.Text(), nullable=True))
    op.add_column("rooms", sa.Column("public_slug", sa.String(180), nullable=True))
    op.add_column(
        "rooms",
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default="0"),
    )
    op.create_index(
        "uq_rooms_public_slug",
        "rooms",
        ["public_slug"],
        unique=True,
        sqlite_where=sa.text("public_slug IS NOT NULL"),
    )

    op.create_table(
        "features",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("scope", sa.String(20), nullable=False),
        sa.Column("category", sa.String(80), nullable=False),
        sa.Column("icon_key", sa.String(100), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="1"),
        sa.CheckConstraint(
            "scope IN ('property', 'room', 'both')", name="ck_features_scope"
        ),
        sa.CheckConstraint(
            "display_order >= 0", name="ck_features_display_order_nonnegative"
        ),
        sa.UniqueConstraint("slug", name="uq_features_slug"),
    )

    op.create_table(
        "media_assets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("storage_key", sa.String(64), nullable=False),
        sa.Column("mime_type", sa.String(50), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("checksum_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="processing"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('processing', 'ready', 'failed')",
            name="ck_media_assets_status",
        ),
        sa.CheckConstraint("width > 0", name="ck_media_assets_width_positive"),
        sa.CheckConstraint("height > 0", name="ck_media_assets_height_positive"),
        sa.CheckConstraint(
            "byte_size > 0", name="ck_media_assets_byte_size_positive"
        ),
        sa.UniqueConstraint("storage_key", name="uq_media_assets_storage_key"),
        sa.UniqueConstraint(
            "checksum_sha256", name="uq_media_assets_checksum_sha256"
        ),
    )

    op.create_table(
        "property_features",
        sa.Column(
            "property_id",
            sa.Integer(),
            sa.ForeignKey("properties.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "feature_id",
            sa.Integer(),
            sa.ForeignKey("features.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_table(
        "room_features",
        sa.Column(
            "room_id",
            sa.Integer(),
            sa.ForeignKey("rooms.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "feature_id",
            sa.Integer(),
            sa.ForeignKey("features.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    op.create_table(
        "property_photos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "property_id",
            sa.Integer(),
            sa.ForeignKey("properties.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "media_asset_id",
            sa.Integer(),
            sa.ForeignKey("media_assets.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default="0"),
        sa.CheckConstraint(
            "position >= 0", name="ck_property_photos_position_nonnegative"
        ),
    )
    op.create_index(
        "uq_property_photos_asset",
        "property_photos",
        ["property_id", "media_asset_id"],
        unique=True,
    )
    op.create_index(
        "uq_property_photos_position",
        "property_photos",
        ["property_id", "position"],
        unique=True,
    )
    op.create_index(
        "uq_property_photos_primary",
        "property_photos",
        ["property_id"],
        unique=True,
        sqlite_where=sa.text("is_primary = 1"),
    )

    op.create_table(
        "room_photos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "room_id",
            sa.Integer(),
            sa.ForeignKey("rooms.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "media_asset_id",
            sa.Integer(),
            sa.ForeignKey("media_assets.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default="0"),
        sa.CheckConstraint(
            "position >= 0", name="ck_room_photos_position_nonnegative"
        ),
    )
    op.create_index(
        "uq_room_photos_asset",
        "room_photos",
        ["room_id", "media_asset_id"],
        unique=True,
    )
    op.create_index(
        "uq_room_photos_position",
        "room_photos",
        ["room_id", "position"],
        unique=True,
    )
    op.create_index(
        "uq_room_photos_primary",
        "room_photos",
        ["room_id"],
        unique=True,
        sqlite_where=sa.text("is_primary = 1"),
    )


def downgrade() -> None:
    op.drop_index("uq_room_photos_primary", table_name="room_photos")
    op.drop_index("uq_room_photos_position", table_name="room_photos")
    op.drop_index("uq_room_photos_asset", table_name="room_photos")
    op.drop_table("room_photos")

    op.drop_index("uq_property_photos_primary", table_name="property_photos")
    op.drop_index("uq_property_photos_position", table_name="property_photos")
    op.drop_index("uq_property_photos_asset", table_name="property_photos")
    op.drop_table("property_photos")

    op.drop_table("room_features")
    op.drop_table("property_features")
    op.drop_table("media_assets")
    op.drop_table("features")

    op.drop_index("uq_rooms_public_slug", table_name="rooms")
    op.drop_column("rooms", "is_published")
    op.drop_column("rooms", "public_slug")
    op.drop_column("rooms", "public_description")
    op.drop_column("rooms", "public_title")

    op.drop_index("uq_properties_public_slug", table_name="properties")
    op.drop_column("properties", "is_published")
    op.drop_column("properties", "public_slug")
    op.drop_column("properties", "public_location")
    op.drop_column("properties", "public_description")
    op.drop_column("properties", "public_title")
