"""Pure monetary rules shared by expenses and owner settlements.

No persistence, inferred custody, tax defaults or ownership lookup lives here.
"""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

ZERO = Decimal("0.00")
CENT = Decimal("0.01")
MAX_AMOUNT = Decimal("9999999999.99")


def money(value, *, signed=False):
    if isinstance(value, (float, bool)):
        raise ValueError("Utilice un importe decimal exacto.")
    try:
        result = Decimal(value)
        if not result.is_finite() or abs(result) > MAX_AMOUNT:
            raise ValueError
        rounded = result.quantize(CENT, rounding=ROUND_HALF_UP)
        if result != rounded or (not signed and rounded < ZERO):
            raise ValueError
        return rounded
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Importe monetario no válido.") from None


@dataclass(frozen=True)
class ExpenseBalance:
    total: Decimal
    paid: Decimal
    unpaid: Decimal
    settled: Decimal
    available: Decimal
    status: str


def expense_balance(total, payments, settled=ZERO):
    """Payments are signed posted movements; reversals remain separate records.

    Negative available is a correction owed back to the owner, not a new
    deductible payment. Consumers must preserve its sign.
    """
    total = money(total)
    paid = sum((money(value, signed=True) for value in payments), ZERO)
    settled = money(settled, signed=True)
    if not ZERO <= paid <= total:
        raise ValueError("Los pagos netos deben estar entre cero y el total del gasto.")
    status = "pending" if paid == ZERO else "paid" if paid == total else "partial"
    return ExpenseBalance(total, paid, total - paid, settled, paid - settled, status)


def percentage_fee(collected, percentage):
    collected = money(collected, signed=True)
    percentage = money(percentage)
    if percentage > Decimal("100"):
        raise ValueError("Porcentaje fuera de rango.")
    return (collected * percentage / Decimal("100")).quantize(CENT, rounding=ROUND_HALF_UP)


def split_money(amount, shares):
    """Largest remainder in cents, stable by owner id, with exact conservation.

    shares is an iterable of (owner_id, percentage). Never normalize incomplete
    ownership or silently merge duplicate owners.
    """
    amount = money(amount, signed=True)
    shares = sorted((owner_id, money(value)) for owner_id, value in shares)
    if (not shares or len({owner for owner, _ in shares}) != len(shares)
            or any(value <= ZERO for _, value in shares)
            or sum((value for _, value in shares), ZERO) != Decimal("100.00")):
        raise ValueError("La titularidad debe ser inequívoca y sumar el 100 %.")
    cents = int(abs(amount) * 100)
    raw = [(owner, Decimal(cents) * value / 100) for owner, value in shares]
    units = {owner: int(value) for owner, value in raw}
    remainder = cents - sum(units.values())
    ranked = sorted(raw, key=lambda item: (-(item[1] - int(item[1])), item[0]))
    for owner, _ in ranked[:remainder]:
        units[owner] += 1
    sign = Decimal("-1") if amount < ZERO else Decimal("1")
    return {owner: (Decimal(value) * CENT * sign) for owner, value in units.items()}


@dataclass(frozen=True)
class SettlementTotals:
    economic_balance: Decimal
    funds_balance: Decimal
    payout_due: Decimal
    carry_forward: Decimal
    period_balance: Decimal
    manager_credit: Decimal


@dataclass(frozen=True)
class OwnerCustody:
    economic_income: Decimal
    directly_received: Decimal
    manager_held_funds: Decimal
    inter_owner_difference: Decimal
    inter_owner_receivable: Decimal
    excess_received: Decimal


def distribute_custody(amount, shares, receipts):
    """Separate economic rights from actual receipts for every co-owner.

    receipts: (recipient owner id or None for manager, amount). A recipient
    can receive more than their share without blocking economic settlement.
    This function creates no transfer, debt or payment.
    """
    amount = money(amount)
    shares = list(shares)
    rights = split_money(amount, shares)
    received = {owner: ZERO for owner in rights}
    manager = ZERO
    for recipient, value in receipts:
        value = money(value)
        if recipient is None:
            manager += value
        elif recipient in received:
            received[recipient] += value
        else:
            raise ValueError("El receptor debe identificarse entre los titulares aplicables.")
    if sum(received.values(), manager) != amount:
        raise ValueError("La distribución de custodia debe coincidir con el cobro.")
    # Attribute manager cash using the same ownership and cent-allocation rule.
    managed = split_money(manager, shares)
    result = {}
    for owner, economic in rights.items():
        difference = received[owner] + managed[owner] - economic
        result[owner] = OwnerCustody(economic, received[owner], managed[owner],
                                    difference, max(ZERO, -difference), max(ZERO, difference))
    return result


def settlement_totals(*, income, expenses, fees, manager_receipts,
                      manager_expenses, adjustments=ZERO, funds_adjustments=ZERO):
    """Fees are deducted once. Direct-owner receipts never become manager cash.

    Negative funds are a debt/carry, even if economic_balance is positive.
    Adjustments to economic and custodial balances are deliberately independent.
    """
    income, expenses, fees, manager_receipts, manager_expenses, adjustments, funds_adjustments = (
        money(value, signed=True) for value in
        (income, expenses, fees, manager_receipts, manager_expenses, adjustments, funds_adjustments)
    )
    economic = income - expenses - fees + adjustments
    funds = manager_receipts - manager_expenses - fees + funds_adjustments
    return SettlementTotals(economic, funds, max(ZERO, funds), min(ZERO, funds),
                            income - expenses - fees, max(ZERO, -funds))
