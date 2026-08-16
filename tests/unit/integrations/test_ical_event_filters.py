from datetime import date

from backend.integrations.ical_event_filters import is_platform_calendar_echo
from backend.integrations.ical_parser import NormalizedIcalEvent


def event(summary: str) -> NormalizedIcalEvent:
    return NormalizedIcalEvent(
        uid="UID",
        check_in=date(2026, 9, 21),
        check_out=date(2026, 9, 27),
        notes=summary,
        cancelled=False,
        summary=summary,
    )


def test_only_proven_housinganywhere_summary_is_an_echo():
    proven = event("Evento importado desde el archivo de calendario")
    assert is_platform_calendar_echo("housinganywhere", proven)
    assert not is_platform_calendar_echo("spotahome", proven)
    assert not is_platform_calendar_echo(
        "housinganywhere", event("Manualmente bloqueado")
    )
    assert not is_platform_calendar_echo(
        "housinganywhere", event("Reservas: Aleksandra")
    )
