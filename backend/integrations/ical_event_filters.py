from backend.integrations.ical_parser import NormalizedIcalEvent


HOUSINGANYWHERE_IMPORTED_CALENDAR_SUMMARY = (
    "Evento importado desde el archivo de calendario"
)


def is_platform_calendar_echo(
    platform_slug: str,
    event: NormalizedIcalEvent,
) -> bool:
    return (
        platform_slug == "housinganywhere"
        and event.summary == HOUSINGANYWHERE_IMPORTED_CALENDAR_SUMMARY
    )
