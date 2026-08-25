from datetime import date
from decimal import Decimal

from backend.public.schemas import (
    PublicAvailabilityDTO,
    PublicImageDTO,
    PublicRoomCardDTO,
)
from backend.public.service import PublicRoomService


TODAY = date(2026, 8, 26)


def card(slug, price, size, *, available_from=None):
    availability = PublicAvailabilityDTO(
        status="available_now" if available_from is None else "available_from",
        available_from=available_from,
    )
    return PublicRoomCardDTO(
        slug=slug,
        title=slug,
        location="Elche",
        price_monthly=Decimal(str(price)),
        square_meters=Decimal(str(size)),
        availability=availability,
        features=(),
        primary_image=PublicImageDTO(
            url_320="/320.webp",
            url_768="/768.webp",
            url_1600="/1600.webp",
            source="room",
            width=1600,
            height=1000,
        ),
    )


def slugs(items, sort):
    return [
        item.slug
        for item in sorted(items, key=PublicRoomService._sort_key(sort, TODAY))
    ]


def test_recommended_orders_by_availability_price_surface_and_stable_slug():
    rooms = [
        card("future", 200, 8, available_from=date(2026, 9, 1)),
        card("larger", 300, 12),
        card("b-stable", 300, 10),
        card("a-stable", 300, 10),
        card("cheaper", 250, 14),
    ]

    assert slugs(rooms, "recommended") == [
        "cheaper", "a-stable", "b-stable", "larger", "future"
    ]
    assert slugs(rooms, "availability")[0] == "cheaper"


def test_explicit_price_and_surface_orders_keep_their_contract():
    rooms = [
        card("small", 400, 8, available_from=date(2026, 9, 10)),
        card("middle", 300, 10, available_from=date(2026, 9, 1)),
        card("large", 200, 14),
    ]

    assert slugs(rooms, "price_asc") == ["large", "middle", "small"]
    assert slugs(rooms, "price_desc") == ["small", "middle", "large"]
    assert slugs(rooms, "size_asc") == ["small", "middle", "large"]
    assert slugs(rooms, "size_desc") == ["large", "middle", "small"]


def test_unknown_sort_falls_back_to_recommended():
    rooms = [card("future", 100, 8, available_from=date(2026, 9, 1)), card("now", 900, 20)]

    assert PublicRoomService.normalize_sort("invalid") == "recommended"
    assert slugs(rooms, "invalid") == slugs(rooms, "recommended") == ["now", "future"]
