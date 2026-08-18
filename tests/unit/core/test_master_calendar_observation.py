from datetime import datetime, timedelta
from types import SimpleNamespace

from backend.core.master_calendar_observation import (
    MASTER_CALENDAR_RECENCY_WINDOW,
    MASTER_CALENDAR_RECURRENCE_MIN_GAP,
    master_calendar_evidence,
)


NOW = datetime(2026, 8, 17, 12, 0)


def calendar(first=None, last=None, count=0):
    return SimpleNamespace(
        master_calendar_first_request_at=first,
        last_master_calendar_request_at=last,
        master_calendar_request_count=count,
    )


def test_never_and_isolated_requests_are_not_recurrent():
    assert master_calendar_evidence(calendar(), NOW).state == "never"
    one = calendar(NOW, NOW, 1)
    assert master_calendar_evidence(one, NOW).state == "isolated"
    close = calendar(
        NOW, NOW + MASTER_CALENDAR_RECURRENCE_MIN_GAP - timedelta(seconds=1), 2
    )
    assert master_calendar_evidence(close, NOW).state == "isolated"


def test_recurrent_consumption_must_also_be_recent():
    recurrent = calendar(
        NOW - timedelta(hours=1), NOW, 2
    )
    assert master_calendar_evidence(recurrent, NOW).state == "recurrent_recent"
    stale_last = NOW - MASTER_CALENDAR_RECENCY_WINDOW - timedelta(seconds=1)
    stale = calendar(stale_last - timedelta(hours=1), stale_last, 2)
    assert master_calendar_evidence(stale, NOW).state == "recurrent_stale"
