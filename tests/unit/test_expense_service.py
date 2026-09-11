from datetime import date
from decimal import Decimal as D
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from backend.models.owner import Owner
from backend.models.property import Property
from backend.models.owner_settlement import Expense, ExpenseCategory, ExpensePayment
from backend.services.expense_service import ExpenseService


@pytest.fixture
def expense(db_session, monkeypatch):
    monkeypatch.setattr("backend.services.expense_service.business_today", lambda: date(2026, 9, 30))
    property_obj = Property(name="Finca sintética", address="Calle de prueba", city="Elche", owner="", active=True)
    category = ExpenseCategory(code="repair", name="Reparación", active=True)
    db_session.add_all([property_obj, category])
    db_session.commit()
    return ExpenseService().create(db_session, property_id=property_obj.id, category_id=category.id,
        expense_date=date(2026, 9, 1), concept="Reparación sintética", base_amount="300",
        vat_rate="0", withholding_rate="0")


def pay(db, expense, **kwargs):
    values = dict(effective_date=date(2026, 9, 15), amount="100", paid_by="manager",
                  request_key=str(uuid4()))
    values.update(kwargs)
    return ExpenseService().pay(db, expense.id, **values)


def test_registered_expense_has_no_automatic_payment(db_session, expense):
    balance = ExpenseService().balance(db_session, expense.id)
    assert balance.status == "pending"
    assert balance.available == D("0")
    assert db_session.scalar(select(func.count()).select_from(ExpensePayment)) == 0


def test_partial_and_full_payments(db_session, expense):
    pay(db_session, expense)
    balance = ExpenseService().balance(db_session, expense.id)
    assert (balance.paid, balance.unpaid, balance.available, balance.status) == (D("100"), D("200"), D("100"), "partial")
    pay(db_session, expense, amount="200")
    assert ExpenseService().balance(db_session, expense.id).status == "paid"


def test_payment_idempotency_and_different_retry(db_session, expense):
    key = str(uuid4())
    first = pay(db_session, expense, request_key=key)
    assert pay(db_session, expense, request_key=key).id == first.id
    with pytest.raises(ValueError):
        pay(db_session, expense, request_key=key, amount="101")
    assert len(ExpenseService().payments(db_session, expense.id)) == 1


def test_reversal_preserves_original_and_reopens_expense(db_session, expense):
    original = pay(db_session, expense, amount="300")
    reversal = pay(db_session, expense, corrects_id=original.id, amount="100")
    assert reversal.direction == "reversal"
    assert db_session.get(ExpensePayment, original.id).amount == D("300")
    assert ExpenseService().balance(db_session, expense.id).paid == D("200")
    with pytest.raises(ValueError):
        pay(db_session, expense, corrects_id=original.id, amount="201")


def test_owner_paid_payment_identifies_actual_owner(db_session, expense):
    owner = Owner(legal_name="Titular sintético", active=True)
    db_session.add(owner)
    db_session.commit()
    payment = pay(db_session, expense, paid_by="owner", paid_by_owner_id=owner.id)
    assert payment.paid_by_owner_id == owner.id
    with pytest.raises(ValueError):
        pay(db_session, expense, paid_by="owner")
    with pytest.raises(ValueError):
        pay(db_session, expense, paid_by="manager", paid_by_owner_id=owner.id)


@pytest.mark.parametrize("values", [
    {"amount": "301"}, {"amount": "-1"}, {"amount": 1.2},
    {"amount": "0"}, {"effective_date": date(2026, 10, 1)},
])
def test_invalid_payment_never_persists(db_session, expense, values):
    with pytest.raises(ValueError):
        pay(db_session, expense, **values)
    assert len(ExpenseService().payments(db_session, expense.id)) == 0


def test_expense_does_not_create_booking_ledger(db_session, expense):
    from backend.models.payment import Payment
    from backend.models.booking_charge import BookingCharge
    pay(db_session, expense)
    assert db_session.scalar(select(func.count()).select_from(Payment)) == 0
    assert db_session.scalar(select(func.count()).select_from(BookingCharge)) == 0
