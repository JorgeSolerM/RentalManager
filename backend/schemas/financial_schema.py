from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class ChargeBalance:
    original_amount: Decimal
    allocated_amount: Decimal
    outstanding_amount: Decimal
    payment_status: str
    overdue: bool


@dataclass(frozen=True)
class BookingLedgerSummary:
    charged_total: Decimal
    received_total: Decimal
    allocated_total: Decimal
    unapplied_balance: Decimal
    outstanding_balance: Decimal
    overdue_balance: Decimal


@dataclass(frozen=True)
class LegacyPriceCandidate:
    amount: Decimal | None
    source: str = "booking.price"
