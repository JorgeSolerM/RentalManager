from __future__ import annotations


def normalize_address_part(value: str | None) -> str | None:
    normalized = " ".join((value or "").split())
    return normalized or None


def format_property_address(property_obj) -> str:
    """Return the internal display address from structured components."""
    street = normalize_address_part(property_obj.street)
    number = normalize_address_part(property_obj.street_number)
    floor = normalize_address_part(property_obj.floor)
    door = normalize_address_part(property_obj.door)

    main = " ".join(part for part in (street, number) if part)
    detail = " ".join(part for part in (floor, door) if part)
    return f"{main}, {detail}" if main and detail else main or detail
