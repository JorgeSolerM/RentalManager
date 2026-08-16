import os
import re


DEFAULT_SYNC_INTERVAL_MINUTES = 10
MAX_BACKOFF_MINUTES = 60


def sync_interval_minutes(platform_slug: str) -> int:
    """Allow future per-platform cadence without storing scheduling in the DB."""
    suffix = re.sub(r"[^A-Z0-9]", "_", platform_slug.upper())
    raw = os.getenv(
        f"ICAL_SYNC_INTERVAL_{suffix}_MINUTES",
        os.getenv("ICAL_SYNC_INTERVAL_MINUTES", str(DEFAULT_SYNC_INTERVAL_MINUTES)),
    )
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_SYNC_INTERVAL_MINUTES
    return value if value > 0 else DEFAULT_SYNC_INTERVAL_MINUTES


def backoff_minutes(consecutive_failures: int) -> int:
    failures = max(1, consecutive_failures)
    return min(DEFAULT_SYNC_INTERVAL_MINUTES * (2 ** (failures - 1)), MAX_BACKOFF_MINUTES)
