from datetime import date, datetime
from zoneinfo import ZoneInfo


BUSINESS_TIMEZONE = ZoneInfo("Europe/Madrid")


def business_today(now: datetime | None = None) -> date:
    current = now or datetime.now(BUSINESS_TIMEZONE)
    if current.tzinfo is None:
        current = current.replace(tzinfo=BUSINESS_TIMEZONE)
    else:
        current = current.astimezone(BUSINESS_TIMEZONE)
    return current.date()
