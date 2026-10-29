from calendar import monthrange
from datetime import date, timedelta
from typing import Iterable


def add_calendar_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, monthrange(year, month)[1])
    return date(year, month, day)


def terminal_available_from(intervals: Iterable[tuple[date, date]], today: date) -> date | None:
    """Availability after ALL known occupancy, never an intermediate gap.

    Input must not be truncated to a display horizon. Checkout is exclusive,
    just as in Gantt/booking_overlap; confirmed early departures already update
    Booking.check_out. Invalid intervals fail closed rather than advertise space.
    """
    result = today
    for start, end in intervals:
        if end <= start:
            return None
        result = max(result, end)
    return result


def stay_within_calendar_month_limits(
    check_in: date,
    check_out: date,
    minimum_months: int,
    maximum_months: int | None,
) -> bool:
    """Validate a requested stay using calendar-month boundaries."""
    if check_out <= check_in:
        return False
    if minimum_months > 0 and check_out < add_calendar_months(check_in, minimum_months):
        return False
    if maximum_months is not None and check_out > add_calendar_months(check_in, maximum_months):
        return False
    return True


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
