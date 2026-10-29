from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from decimal import Decimal as D
from uuid import uuid4

import pytest
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from backend.models import Owner
from backend.models.owner_settlement import OwnerSettlement, OwnerSettlementLine
from backend.models.fee_billing import FeeObligation, FeeFund, FeeCompensation, FeeCompensationRun
from backend.services.fee_compensation_service import FeeCompensationService
from tests.unit.test_owner_settlement_service import sample, draft, service as settlements

service = FeeCompensationService()


def setup_sources(db, sample, *, expense=True):
    settlement = draft(db, sample)
    settlements.close(db, settlement.id, settlement.fingerprint)
    line = db.scalar(select(OwnerSettlementLine).where(OwnerSettlementLine.settlement_id == settlement.id))
    sources = []
    for kind, amount in ([('expense_advance', '500'), ('management_fee', '60')] if expense else []):
        row = FeeObligation(owner_id=settlement.owner_id, settlement_id=settlement.id,
            source_line_id=line.id, source_key=kind, kind=kind, effective_date=date(2026, 9, 1),
            amount=D(amount), snapshot={'synthetic': True})
        db.add(row)
        sources.append(row)
    fund = FeeFund(owner_id=settlement.owner_id, settlement_id=settlement.id,
        source_line_id=line.id, effective_date=date(2026, 9, 15), amount=D('300'))
    db.add(fund)
    db.commit()
    return settlement, fund, sources


def apply(db, settlement, fund, key=None):
    return service.apply(db, fund_id=fund.id, settlement_id=settlement.id,
                         effective_date=date(2026, 9, 30), request_key=key or str(uuid4()))


def test_persistent_partial_applications_idempotency_and_history(db_session, sample):
    settlement, fund, obligations = setup_sources(db_session, sample)
    original = dict(settlement.snapshot)
    key = str(uuid4())
    rows = apply(db_session, settlement, fund, key)
    assert len(rows) == 1 and rows[0].obligation_id == obligations[0].id and rows[0].amount == 300
    assert [r.id for r in apply(db_session, settlement, fund, key)] == [rows[0].id]
    assert apply(db_session, settlement, fund) == []  # no remaining funds
    balances = service.balances(db_session, settlement.owner_id)
    assert [(r.generated, r.compensated, r.outstanding) for r in balances] == [
        (D('500'), D('300'), D('200')), (D('60'), D('0'), D('60'))]
    db_session.refresh(settlement)
    assert settlement.snapshot == original and settlement.status == 'closed'
    assert db_session.scalar(select(func.count()).select_from(FeeObligation)) == 2


def test_reversal_is_append_only_and_reopens_obligation(db_session, sample):
    settlement, fund, _ = setup_sources(db_session, sample)
    original = apply(db_session, settlement, fund)[0]
    key = str(uuid4())
    kwargs = dict(application_id=original.id, settlement_id=settlement.id, amount='100',
        effective_date=date(2026, 10, 1), reason='Corrección sintética', request_key=key)
    correction = service.reverse(db_session, **kwargs)
    assert service.reverse(db_session, **kwargs).id == correction.id
    assert original.amount == 300 and original.direction == 'application'
    assert service.fund_available(db_session, fund) == 100
    assert service.balances(db_session, settlement.owner_id)[0].outstanding == 300
    with pytest.raises(ValueError, match='supera'):
        service.reverse(db_session, **{**kwargs, 'amount': '201', 'request_key': str(uuid4())})
    assert db_session.scalar(select(func.count()).select_from(FeeCompensation)) == 2


def test_noop_request_cannot_acquire_new_debt_on_retry(db_session, sample):
    settlement, fund, _ = setup_sources(db_session, sample, expense=False)
    key = str(uuid4())
    assert apply(db_session, settlement, fund, key) == []
    db_session.add(FeeObligation(owner_id=settlement.owner_id, settlement_id=settlement.id,
        source_line_id=fund.source_line_id, source_key='late', kind='management_fee',
        effective_date=date(2026, 9, 1), amount=D('60'), snapshot={}))
    db_session.commit()
    assert apply(db_session, settlement, fund, key) == []
    assert len(apply(db_session, settlement, fund)) == 1


def test_concurrent_applications_never_consume_funds_twice(db_session, sample):
    settlement, fund, _ = setup_sources(db_session, sample)
    engine = db_session.get_bind()
    sid, fid = settlement.id, fund.id
    db_session.rollback()
    def attempt(_):
        with Session(engine) as db:
            return sum((r.amount for r in service.apply(db, fund_id=fid, settlement_id=sid,
                effective_date=date(2026, 9, 30), request_key=str(uuid4()))), D('0'))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, range(2)))
    assert sum(results) == 300
    assert db_session.scalar(select(func.sum(FeeCompensation.amount))) == 300


def test_failure_rolls_back_request_and_applications(db_session, sample, monkeypatch):
    settlement, fund, _ = setup_sources(db_session, sample)
    def fail(*args):
        raise ValueError('synthetic_failure')
    monkeypatch.setattr(service, 'balances', fail)
    with pytest.raises(ValueError, match='synthetic_failure'):
        apply(db_session, settlement, fund)
    assert db_session.scalar(select(func.count()).select_from(FeeCompensationRun)) == 0
    assert db_session.scalar(select(func.count()).select_from(FeeCompensation)) == 0
