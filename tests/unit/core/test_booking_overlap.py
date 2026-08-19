from datetime import date

from backend.core.booking_overlap import intervals_overlap, is_operational_overlap


TODAY = date(2026, 8, 17)


def test_geometric_overlap_is_independent_from_business_date():
    assert intervals_overlap(
        date(2026, 5, 8), date(2026, 8, 31),
        date(2026, 4, 13), date(2026, 5, 31),
    )
    assert not intervals_overlap(
        date(2026, 9, 1), date(2026, 9, 5),
        date(2026, 9, 5), date(2026, 9, 10),
    )


def test_only_intersections_ending_after_today_are_operational():
    assert not is_operational_overlap(
        date(2026, 4, 1), date(2026, 4, 30),
        date(2026, 4, 13), date(2026, 5, 31), TODAY,
    )
    assert not is_operational_overlap(
        date(2026, 8, 10), TODAY,
        date(2026, 8, 1), date(2026, 8, 16), TODAY,
    )
    assert is_operational_overlap(
        date(2026, 8, 10), date(2026, 8, 20),
        date(2026, 8, 15), date(2026, 8, 25), TODAY,
    )
    assert is_operational_overlap(
        date(2026, 9, 10), date(2026, 9, 20),
        date(2026, 9, 15), date(2026, 9, 25), TODAY,
    )


def test_rule_is_symmetric_when_one_booking_continues_into_future():
    assert not is_operational_overlap(
        date(2026, 4, 13), date(2026, 5, 31),
        date(2026, 5, 8), date(2026, 8, 31), TODAY,
    )
    assert not is_operational_overlap(
        date(2026, 5, 8), date(2026, 8, 31),
        date(2026, 4, 13), date(2026, 5, 31), TODAY,
    )


def test_contiguous_and_different_intervals_do_not_conflict():
    assert not is_operational_overlap(
        date(2026, 9, 1), date(2026, 9, 5),
        date(2026, 9, 5), date(2026, 9, 10), TODAY,
    )
