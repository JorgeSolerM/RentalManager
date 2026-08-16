import logging
from pathlib import Path

from backend.core.logging import MasterCalendarTokenFilter


def test_master_calendar_token_is_redacted_from_access_log_arguments():
    token = "a-secret-master-calendar-token"
    record = logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg='%s - "%s %s HTTP/%s" %d',
        args=(
            "127.0.0.1:1",
            "GET",
            f"/ical/rooms/{token}/housinganywhere.ics?probe=1",
            "1.1",
            200,
        ),
        exc_info=None,
    )

    assert MasterCalendarTokenFilter().filter(record)
    rendered = record.getMessage()
    assert token not in rendered
    assert "/ical/rooms/[redacted]/housinganywhere.ics" in rendered


def test_master_calendar_revocation_confirmation_explains_operational_effects():
    script = Path("backend/static/js/master_calendar.js").read_text(encoding="utf-8")
    assert "dejarán de funcionar inmediatamente" in script
    assert "HousingAnywhere, Flatio, Spotahome" in script
    assert "No es necesario hacer esto cuando cambian las reservas" in script
    assert "manteniendo las mismas URLs" in script
