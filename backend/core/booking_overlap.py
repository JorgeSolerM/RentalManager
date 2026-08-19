from datetime import date


def intervals_overlap(
    first_check_in: date,
    first_check_out: date,
    second_check_in: date,
    second_check_out: date,
) -> bool:
    return (
        first_check_in < second_check_out
        and first_check_out > second_check_in
    )


def is_operational_overlap(
    first_check_in: date,
    first_check_out: date,
    second_check_in: date,
    second_check_out: date,
    business_date: date,
) -> bool:
    if not intervals_overlap(
        first_check_in,
        first_check_out,
        second_check_in,
        second_check_out,
    ):
        return False
    overlap_end = min(first_check_out, second_check_out)
    return overlap_end > business_date


def booking_intervals_overlap(
    first_check_in: date,
    first_check_out: date,
    second_check_in: date,
    second_check_out: date,
) -> bool:
    """Backward-compatible domain alias for geometric overlap."""
    return intervals_overlap(
        first_check_in,
        first_check_out,
        second_check_in,
        second_check_out,
    )


def booking_intervals_conflict(
    candidate_check_in: date,
    candidate_check_out: date,
    existing_check_in: date,
    existing_check_out: date,
    business_date: date,
) -> bool:
    """Backward-compatible alias for an operational overlap."""
    return is_operational_overlap(
        candidate_check_in,
        candidate_check_out,
        existing_check_in,
        existing_check_out,
        business_date,
    )
