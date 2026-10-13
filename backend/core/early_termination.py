"""Early departure dates use the existing half-open occupancy convention."""
from datetime import timedelta


def economic_end_exclusive(last_charge_day):
    return last_charge_day + timedelta(days=1)
