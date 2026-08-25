"""managers and room public highlights

Revision ID: b1d3f5a7c902
Revises: a8c1e4f6b209
"""

from alembic import op
import sqlalchemy as sa


revision = "b1d3f5a7c902"
down_revision = "a8c1e4f6b209"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "managers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("media_asset_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["media_asset_id"], ["media_assets.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_managers_media_asset_id", "managers", ["media_asset_id"])
    # SQLite accepts a nullable REFERENCES column in ADD COLUMN, but Alembic's
    # generic add_column implementation tries to add the FK separately via an
    # unsupported ALTER TABLE ADD CONSTRAINT operation.
    op.execute(
        "ALTER TABLE properties ADD COLUMN manager_id INTEGER "
        "REFERENCES managers(id) ON DELETE SET NULL"
    )
    op.create_index("ix_properties_manager_id", "properties", ["manager_id"])
    op.create_table(
        "room_public_highlights",
        sa.Column("room_id", sa.Integer(), nullable=False),
        sa.Column("feature_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.CheckConstraint("position >= 0 AND position < 4", name="ck_room_public_highlights_position"),
        sa.ForeignKeyConstraint(["feature_id"], ["features.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("room_id", "feature_id"),
        sa.UniqueConstraint("room_id", "position", name="uq_room_public_highlights_position"),
    )
    op.execute(
        "INSERT OR IGNORE INTO features "
        "(slug,name,scope,category,icon_key,display_order,active) VALUES "
        "('suministros-incluidos','Suministros incluidos','property','Condiciones',NULL,160,1)"
    )


def downgrade():
    op.drop_table("room_public_highlights")
    op.drop_index("ix_properties_manager_id", table_name="properties")
    op.drop_column("properties", "manager_id")
    op.drop_index("ix_managers_media_asset_id", table_name="managers")
    op.drop_table("managers")
