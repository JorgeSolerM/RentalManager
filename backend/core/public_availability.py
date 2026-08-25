from calendar import monthrange
from datetime import date, timedelta
from typing import Iterable


def add_calendar_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, monthrange(year, month)[1])
    return date(year, month, day)


def first_commercial_gap(
    intervals: Iterable[tuple[date, date]],
    today: date,
    minimum_stay_months: int,
) -> tuple[str, date | None, date | None]:
    relevant = sorted(
        ((start, end) for start, end in intervals if end > today),
        key=lambda interval: interval,
    )
    merged: list[tuple[date, date]] = []
    for start, end in relevant:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

    cursor = today
    for start, end in merged:
        if end <= cursor:
            continue
        if start > cursor:
            minimum_end = add_calendar_months(cursor, minimum_stay_months)
            if minimum_stay_months == 0 or minimum_end <= start:
                return "available_period", cursor, start - timedelta(days=1)
        cursor = max(cursor, end)

    if cursor == today:
        return "available_now", None, None
    return "available_from", cursor, None
