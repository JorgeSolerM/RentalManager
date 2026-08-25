"""Add Room minimum and maximum stay in calendar months.

Revision ID: c4e6a8b0d214
Revises: b1d3f5a7c902
"""

import sqlalchemy as sa
from alembic import op


revision = "c4e6a8b0d214"
down_revision = "b1d3f5a7c902"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
    with op.batch_alter_table("rooms") as batch_op:
        batch_op.add_column(sa.Column("minimum_stay_months", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("maximum_stay_months", sa.Integer(), nullable=True))
        batch_op.create_check_constraint(
            "ck_rooms_minimum_stay_months_nonnegative",
            "minimum_stay_months IS NULL OR minimum_stay_months >= 0",
        )
        batch_op.create_check_constraint(
            "ck_rooms_maximum_stay_months_positive",
            "maximum_stay_months IS NULL OR maximum_stay_months > 0",
        )
        batch_op.create_check_constraint(
            "ck_rooms_stay_months_compatible",
            "minimum_stay_months IS NULL OR maximum_stay_months IS NULL "
            "OR minimum_stay_months = 0 OR maximum_stay_months >= minimum_stay_months",
        )
    if connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall():
        raise RuntimeError("Room stay-month migration produced foreign key violations")


def downgrade() -> None:
    connection = op.get_bind()
    connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
    with op.batch_alter_table("rooms") as batch_op:
        batch_op.drop_constraint("ck_rooms_stay_months_compatible", type_="check")
        batch_op.drop_constraint("ck_rooms_maximum_stay_months_positive", type_="check")
        batch_op.drop_constraint("ck_rooms_minimum_stay_months_nonnegative", type_="check")
        batch_op.drop_column("maximum_stay_months")
        batch_op.drop_column("minimum_stay_months")
    if connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall():
        raise RuntimeError("Room stay-month downgrade produced foreign key violations")
