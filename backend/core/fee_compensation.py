"""Pure, deterministic cash application. No new debts for unpaid remainders."""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from backend.services.settlement_money import ZERO, money

KINDS = {'expense_advance': 0, 'management_fee': 1, 'other_adjustment': 2}


@dataclass(frozen=True)
class Obligation:
    key: str
    owner_id: int
    kind: str
    effective_date: date
    generated: Decimal
    compensated: Decimal = ZERO

    @property
    def outstanding(self):
        return self.generated - self.compensated


def compensation_plan(owner_id, funds, obligations):
    available = money(funds)
    rows = list(obligations)
    if len({r.key for r in rows}) != len(rows):
        raise ValueError('Obligaciones duplicadas.')
    for row in rows:
        if row.owner_id != owner_id or row.kind not in KINDS or not isinstance(row.effective_date, date):
            raise ValueError('Obligación ajena al propietario o no válida.')
        if money(row.generated) < money(row.compensated):
            raise ValueError('La compensación supera la obligación.')
    applications = []
    for row in sorted(rows, key=lambda r: (r.effective_date, KINDS[r.kind], r.key)):
        amount = min(available, money(row.generated) - money(row.compensated))
        if amount > ZERO:
            applications.append(dict(obligation_key=row.key, amount=str(amount)))
            available -= amount
    return dict(applications=applications, available=str(available),
                pending=str(sum((money(r.generated) - money(r.compensated) for r in rows), ZERO) - (money(funds)-available)))
