from backend.models.booking import Booking


HOUSINGANYWHERE_MANUAL_BLOCK_SUMMARY = "Manualmente bloqueado"


def persisted_summary(booking: Booking) -> str | None:
    if not booking.notes:
        return None
    first_block = booking.notes.split("\n\n", 1)[0]
    normalized = " ".join(first_block.split())
    return normalized or None


def is_external_manual_block(booking: Booking) -> bool:
    calendar = booking.room_calendar
    return bool(
        calendar is not None
        and booking.external_reference
        and calendar.platform.slug == "housinganywhere"
        and persisted_summary(booking) == HOUSINGANYWHERE_MANUAL_BLOCK_SUMMARY
    )


def external_block_presence(booking: Booking) -> str:
    calendar = booking.room_calendar
    if calendar is None or calendar.feed_presence_tracking_started_at is None:
        return "unknown"
    if calendar.last_sync_at is None:
        return "unknown"
    if (
        booking.last_seen_in_feed_at is not None
        and booking.last_seen_in_feed_at >= calendar.last_sync_at
    ):
        return "present"
    return "disappeared"


def can_delete_external_block(booking: Booking) -> bool:
    return (
        is_external_manual_block(booking)
        and external_block_presence(booking) == "disappeared"
    )
