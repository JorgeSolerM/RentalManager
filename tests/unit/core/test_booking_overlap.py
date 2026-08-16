from datetime import date

from backend.core.booking_overlap import booking_intervals_conflict


TODAY = date(2026, 8, 17)


def test_only_completely_historical_overlaps_are_allowed():
    assert not booking_intervals_conflict(
        date(2026, 4, 1), date(2026, 4, 30),
        date(2026, 4, 13), date(2026, 5, 31), TODAY,
    )
    assert booking_intervals_conflict(
        date(2026, 8, 10), TODAY,
        date(2026, 8, 1), date(2026, 8, 16), TODAY,
    )
    assert booking_intervals_conflict(
        date(2026, 8, 10), date(2026, 8, 20),
        date(2026, 8, 15), date(2026, 8, 25), TODAY,
    )


def test_historical_candidate_may_overlap_an_operational_booking():
    assert not booking_intervals_conflict(
        date(2026, 4, 13), date(2026, 5, 31),
        date(2026, 5, 8), date(2026, 8, 31), TODAY,
    )
    assert booking_intervals_conflict(
        date(2026, 5, 8), date(2026, 8, 31),
        date(2026, 4, 13), date(2026, 5, 31), TODAY,
    )


def test_contiguous_and_different_intervals_do_not_conflict():
    assert not booking_intervals_conflict(
        date(2026, 9, 1), date(2026, 9, 5),
        date(2026, 9, 5), date(2026, 9, 10), TODAY,
    )
