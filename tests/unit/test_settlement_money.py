from decimal import Decimal as D

import pytest

from backend.services.settlement_money import (
    distribute_custody, expense_balance, money, percentage_fee, settlement_totals, split_money,
)


@pytest.mark.parametrize("payments,status,paid,available", [
    ([], "pending", "0", "0"),
    (["100"], "partial", "100", "100"),
    (["100", "200"], "paid", "300", "300"),
    (["300", "-100"], "partial", "200", "200"),
])
def test_expense_cash_basis(payments, status, paid, available):
    balance = expense_balance("300", payments)
    assert balance.status == status
    assert balance.paid == D(paid)
    assert balance.available == D(available)
    assert balance.unpaid == D("300") - D(paid)


def test_partial_consumption_and_post_settlement_reversal():
    assert expense_balance("300", ["100"], "60").available == D("40")
    assert expense_balance("300", ["300", "-100"], "300").available == D("-100")


@pytest.mark.parametrize("payments", [["301"], ["100", "-101"]])
def test_invalid_payment_balance(payments):
    with pytest.raises(ValueError):
        expense_balance("300", payments)


@pytest.mark.parametrize("value", [1.1, True, "NaN", "Infinity", "1.001", "-1"])
def test_money_rejects_inexact_or_invalid_values(value):
    with pytest.raises(ValueError):
        money(value)


def test_approved_example_and_fee_base():
    fee = percentage_fee("1520", "20")
    assert fee == D("304")
    result = settlement_totals(income="1520", expenses="104.54", fees=fee,
                               manager_receipts="1520", manager_expenses="104.54")
    assert result.economic_balance == result.payout_due == D("1111.46")


def test_direct_owner_receipt_never_generates_payout():
    result = settlement_totals(income="500", expenses="0", fees="100",
                               manager_receipts="0", manager_expenses="0")
    assert result.economic_balance == D("400")
    assert result.payout_due == D("0")
    assert result.carry_forward == D("-100")


def test_owner_paid_expense_not_deducted_twice_from_manager_funds():
    result = settlement_totals(income="500", expenses="100", fees="0",
                               manager_receipts="500", manager_expenses="0")
    assert result.economic_balance == D("400")
    assert result.payout_due == D("500")


def test_return_reverses_original_fee():
    assert percentage_fee("-400", "20") == D("-80")
    result = settlement_totals(income="-400", expenses="0", fees="-80",
                               manager_receipts="-400", manager_expenses="0")
    assert result.carry_forward == D("-320")


def test_coownership_rounding_preserves_cents_and_reversal():
    shares = [(2, "50"), (1, "50")]
    assert split_money("100.01", shares) == {1: D("50.01"), 2: D("50.00")}
    assert split_money("-100.01", shares) == {1: D("-50.01"), 2: D("-50.00")}


@pytest.mark.parametrize("shares", [[(1, "50")], [(1, "60"), (2, "60")],
                                          [(1, "50"), (1, "50")], []])
def test_invalid_ownership_blocks(shares):
    with pytest.raises(ValueError):
        split_money("100", shares)


def test_copropietor_receipt_is_warning_not_blocker():
    result = distribute_custody("500", [(1, "50"), (2, "50")], [(1, "500")])
    assert result[1].economic_income == result[2].economic_income == D("250")
    assert result[1].directly_received == D("500")
    assert result[1].excess_received == D("250")
    assert result[2].inter_owner_receivable == D("250")
    assert result[1].manager_held_funds == result[2].manager_held_funds == D("0")
    for owner in result.values():
        total = settlement_totals(income=owner.economic_income, expenses="0", fees="50",
                                  manager_receipts=owner.manager_held_funds, manager_expenses="0")
        assert total.payout_due == D("0")
        assert total.economic_balance == D("200")


@pytest.mark.parametrize("receipts,direct,managed", [
    ([(None, "500")], "0", "250"),
    ([(1, "250"), (2, "250")], "250", "0"),
])
def test_balanced_custody(receipts, direct, managed):
    result = distribute_custody("500", [(1, "50"), (2, "50")], receipts)
    for row in result.values():
        assert row.directly_received == D(direct)
        assert row.manager_held_funds == D(managed)
        assert row.inter_owner_difference == D("0")
        assert percentage_fee(row.economic_income, "20") == D("50")


def test_sole_owner_direct_receipt():
    row = distribute_custody("500", [(1, "100")], [(1, "500")])[1]
    assert row.inter_owner_difference == D("0")
    assert row.directly_received == row.economic_income == D("500")


def test_mixed_custody_conserves_rights_and_differences():
    rows = distribute_custody("500", [(1, "50"), (2, "50")], [(None, "200"), (1, "300")])
    assert rows[1].manager_held_funds == rows[2].manager_held_funds == D("100")
    assert rows[1].excess_received == rows[2].inter_owner_receivable == D("150")
    assert sum(r.inter_owner_difference for r in rows.values()) == D("0")


@pytest.mark.parametrize('received,prior,final,credit,payout',[
    ('0','-200','-200','200','0'),
    ('100','-200','-100','100','0'),
    ('700','-200','500','0','500'),
])
def test_credit_compensation(received,prior,final,credit,payout):
    totals=settlement_totals(income=received,expenses='0',fees='0',manager_receipts=received,
        manager_expenses='0',adjustments=prior,funds_adjustments=prior)
    assert totals.period_balance==D(received)
    assert totals.economic_balance==D(final)
    assert totals.manager_credit==D(credit)
    assert totals.payout_due==D(payout)


def test_owner_paid_expense_does_not_invent_manager_credit():
    totals=settlement_totals(income='0',expenses='500',fees='0',manager_receipts='0',manager_expenses='0')
    assert totals.economic_balance==D('-500')
    assert totals.manager_credit==totals.payout_due==D('0')
