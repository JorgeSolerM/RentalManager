import logging
import re


_MASTER_CALENDAR_PATH = re.compile(r"(/ical/rooms/)[^/?]+(/[^?\s]+)")


class MasterCalendarTokenFilter(logging.Filter):
    """Remove public calendar credentials from Uvicorn access-log paths."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            values = list(record.args)
            for index, value in enumerate(values):
                if isinstance(value, str) and "/ical/rooms/" in value:
                    values[index] = _MASTER_CALENDAR_PATH.sub(
                        r"\1[redacted]\2", value
                    )
            record.args = tuple(values)
        return True


def configure_sensitive_url_logging() -> None:
    logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(item, MasterCalendarTokenFilter) for item in logger.filters):
        logger.addFilter(MasterCalendarTokenFilter())
