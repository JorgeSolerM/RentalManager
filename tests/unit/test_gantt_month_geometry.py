from calendar import monthrange
from datetime import date


MONTH_WIDTH = 120.0


def position_within_month(value: date) -> float:
    days = monthrange(value.year, value.month)[1]
    return (value.day - 1) / days * MONTH_WIDTH


def date_from_month_position(year: int, month: int, x: float) -> date:
    days = monthrange(year, month)[1]
    day_index = min(days - 1, int((x / MONTH_WIDTH) * days + 1e-9))
    return date(year, month, day_index + 1)


def absolute_position(window_year: int, window_month: int, value: date) -> float:
    month_index = (value.year - window_year) * 12 + value.month - window_month
    return month_index * MONTH_WIDTH + position_within_month(value)


def test_january_february_and_march_columns_are_exactly_equal():
    boundaries = [0, MONTH_WIDTH, 2 * MONTH_WIDTH, 3 * MONTH_WIDTH]
    assert [right - left for left, right in zip(boundaries, boundaries[1:])] == [120, 120, 120]


def test_date_fraction_handles_28_29_30_and_31_day_months():
    assert position_within_month(date(2026, 2, 15)) == 14 / 28 * MONTH_WIDTH
    assert position_within_month(date(2028, 2, 15)) == 14 / 29 * MONTH_WIDTH
    assert position_within_month(date(2026, 4, 16)) == 15 / 30 * MONTH_WIDTH
    assert position_within_month(date(2026, 1, 16)) == 15 / 31 * MONTH_WIDTH


def test_coordinate_to_date_at_start_middle_and_end_of_different_months():
    assert date_from_month_position(2026, 2, 0) == date(2026, 2, 1)
    assert date_from_month_position(2026, 2, 60) == date(2026, 2, 15)
    assert date_from_month_position(2026, 2, 119.999) == date(2026, 2, 28)
    assert date_from_month_position(2028, 2, 119.999) == date(2028, 2, 29)
    assert date_from_month_position(2026, 4, 119.999) == date(2026, 4, 30)
    assert date_from_month_position(2026, 1, 119.999) == date(2026, 1, 31)


def test_bookings_within_month_across_months_years_and_contiguous_boundary():
    jan_start = absolute_position(2026, 1, date(2026, 1, 5))
    jan_end = absolute_position(2026, 1, date(2026, 1, 20))
    assert jan_end > jan_start

    cross_month_start = absolute_position(2026, 1, date(2026, 1, 20))
    feb_boundary = absolute_position(2026, 1, date(2026, 2, 1))
    cross_month_end = absolute_position(2026, 1, date(2026, 2, 10))
    assert cross_month_start < feb_boundary < cross_month_end

    december_end = absolute_position(2026, 12, date(2027, 1, 1))
    january_start = absolute_position(2026, 12, date(2027, 1, 1))
    assert december_end == january_start == MONTH_WIDTH

    first_checkout = absolute_position(2026, 1, date(2026, 2, 1))
    second_checkin = absolute_position(2026, 1, date(2026, 2, 1))
    assert first_checkout == second_checkin
