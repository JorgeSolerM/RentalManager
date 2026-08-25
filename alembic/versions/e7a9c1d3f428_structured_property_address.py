"""Add structured Property address fields.

Revision ID: e7a9c1d3f428
Revises: d5f7a9c1e326
"""

import re

import sqlalchemy as sa
from alembic import op


revision = "e7a9c1d3f428"
down_revision = "d5f7a9c1e326"
branch_labels = None
depends_on = None


_BASE_PATTERN = re.compile(
    r"^(?P<street>.+?)\s+(?P<number>\d+[A-Za-z]?)"
    r"(?:\s+(?P<remainder>.+))?$"
)
_FLOOR_ONLY = {"entlo", "entresuelo", "bajo", "bj"}


def _parse_unambiguous_address(value: str | None):
    normalized = " ".join((value or "").split())
    match = _BASE_PATTERN.fullmatch(normalized)
    if not match:
        return None
    street = match.group("street")
    number = match.group("number")
    remainder = match.group("remainder")
    if remainder is None:
        return street, number, None, None
    parts = remainder.split()
    if len(parts) == 1 and parts[0].casefold() in _FLOOR_ONLY:
        return street, number, parts[0], None
    if len(parts) == 2:
        return street, number, parts[0], parts[1]
    # Compact values such as ``4d`` are deliberately left untouched because
    # floor and door cannot be separated without guessing.
    return None


def upgrade() -> None:
    op.add_column("properties", sa.Column("street", sa.String(180), nullable=True))
    op.add_column(
        "properties", sa.Column("street_number", sa.String(30), nullable=True)
    )
    op.add_column("properties", sa.Column("floor", sa.String(30), nullable=True))
    op.add_column("properties", sa.Column("door", sa.String(30), nullable=True))

    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT id, address FROM properties")).mappings()
    for row in rows:
        parsed = _parse_unambiguous_address(row["address"])
        if parsed is None:
            continue
        street, number, floor, door = parsed
        connection.execute(
            sa.text(
                "UPDATE properties SET street=:street, street_number=:number, "
                "floor=:floor, door=:door WHERE id=:id"
            ),
            {
                "id": row["id"],
                "street": street,
                "number": number,
                "floor": floor,
                "door": door,
            },
        )


def downgrade() -> None:
    op.drop_column("properties", "door")
    op.drop_column("properties", "floor")
    op.drop_column("properties", "street_number")
    op.drop_column("properties", "street")
