from datetime import datetime
from types import SimpleNamespace

from backend.core.external_booking_policy import (
    can_delete_external_block,
    external_block_presence,
    is_external_manual_block,
)


NOW = datetime(2026, 8, 19, 10, 0)


def booking(summary="Manualmente bloqueado", slug="housinganywhere"):
    platform = SimpleNamespace(slug=slug)
    calendar = SimpleNamespace(
        platform=platform,
        feed_presence_tracking_started_at=None,
        last_sync_at=None,
    )
    return SimpleNamespace(
        notes=summary,
        external_reference="UID-1",
        room_calendar=calendar,
        last_seen_in_feed_at=None,
    )


def test_only_demonstrated_housinganywhere_manual_block_is_classified():
    assert is_external_manual_block(booking())
    assert not is_external_manual_block(booking("Reservas: Ana"))
    assert not is_external_manual_block(booking("Reserved by Dylan (Flatio)", "flatio"))
    assert not is_external_manual_block(booking("Spotahome", "spotahome"))


def test_presence_requires_tracking_and_compares_last_successful_sync():
    item = booking()
    assert external_block_presence(item) == "unknown"
    item.room_calendar.feed_presence_tracking_started_at = NOW
    item.room_calendar.last_sync_at = NOW
    assert external_block_presence(item) == "disappeared"
    assert can_delete_external_block(item)
    item.last_seen_in_feed_at = NOW
    assert external_block_presence(item) == "present"
    assert not can_delete_external_block(item)
