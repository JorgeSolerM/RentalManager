from datetime import datetime
from zoneinfo import ZoneInfo

from backend.core.business_time import business_today


def test_business_today_uses_madrid_across_midnight_and_dst():
    utc = ZoneInfo("UTC")
    assert business_today(
        datetime(2026, 3, 28, 23, 30, tzinfo=utc)
    ).isoformat() == "2026-03-29"
    assert business_today(
        datetime(2026, 10, 24, 22, 30, tzinfo=utc)
    ).isoformat() == "2026-10-25"
