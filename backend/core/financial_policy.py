"""Central monetary and recurring-charge policy for RentalManager."""

from decimal import Decimal, ROUND_HALF_UP

DEFAULT_CURRENCY = "EUR"
DEFAULT_DUE_DAY = 1
RENT_PERIODICITY = "calendar_month"
PRORATION_POLICY = "actual_calendar_days"
RENT_CHANGE_EFFECTIVE_POLICY = "first_day_of_calendar_month"
MONEY_QUANTUM = Decimal("0.01")
MONEY_ROUNDING = ROUND_HALF_UP


def round_money(value: Decimal) -> Decimal:
    """Round each independently generated charge to cents, half away from zero."""
    return value.quantize(MONEY_QUANTUM, rounding=MONEY_ROUNDING)
