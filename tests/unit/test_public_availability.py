from datetime import date

from backend.core.public_availability import add_calendar_months, first_commercial_gap


def test_short_gap_is_valid_without_minimum_and_skipped_with_positive_minimum():
    today = date(2026, 9, 1)
    intervals = [(date(2026, 9, 15), date(2026, 12, 20))]
    assert first_commercial_gap(intervals, today, 0) == (
        "available_period", today, date(2026, 9, 14)
    )
    assert first_commercial_gap(intervals, today, 2) == (
        "available_from", date(2026, 12, 20), None
    )


def test_minimum_uses_natural_calendar_months_including_month_end():
    assert add_calendar_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_calendar_months(date(2028, 1, 31), 1) == date(2028, 2, 29)
    assert first_commercial_gap(
        [(date(2026, 3, 31), date(2026, 5, 1))], date(2026, 1, 31), 2
    ) == ("available_period", date(2026, 1, 31), date(2026, 3, 30))
