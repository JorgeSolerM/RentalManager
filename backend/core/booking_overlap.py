from datetime import date


def booking_intervals_overlap(
    first_check_in: date,
    first_check_out: date,
    second_check_in: date,
    second_check_out: date,
) -> bool:
    return (
        first_check_in < second_check_out
        and first_check_out > second_check_in
    )


def booking_intervals_conflict(
    candidate_check_in: date,
    candidate_check_out: date,
    existing_check_in: date,
    existing_check_out: date,
    business_date: date,
) -> bool:
    if candidate_check_out < business_date:
        return False
    return booking_intervals_overlap(
        candidate_check_in,
        candidate_check_out,
        existing_check_in,
        existing_check_out,
    )
