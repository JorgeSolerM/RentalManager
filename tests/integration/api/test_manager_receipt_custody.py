from sqlalchemy import select, func
import pytest

from backend.models.owner_settlement import PaymentCustody
from backend.models.payment import Payment
from backend.models.sepa_collection import SepaDebit
from backend.services.payment_custody_service import record_manager_receipt
from tests.integration.api.test_sepa_collections import scenario, create, COLLECTION
from tests.integration.api.test_manual_payments_and_returns import manual, pay


def assert_manager(db, payment):
    rows = list(db.scalars(select(PaymentCustody).where(PaymentCustody.payment_id == payment.id)))
    assert len(rows) == 1
    assert rows[0].actor == 'manager' and rows[0].owner_id is None
    assert rows[0].amount == payment.amount


def test_new_manual_payment_has_explicit_manager_custody(db_session, scenario, manual):
    assert_manager(db_session, pay(db_session, scenario, manual))


def test_sepa_bank_ownership_does_not_determine_custody(db_session, scenario):
    service = scenario[0]
    batch = create(db_session, scenario)
    service.export(db_session, batch.id)
    service.present(db_session, batch.id)
    debit = db_session.scalar(select(SepaDebit))
    assert scenario[2].owner_id is not None
    service.collect(db_session, batch.id, [debit.id], COLLECTION)
    service.collect(db_session, batch.id, [debit.id], COLLECTION)
    assert_manager(db_session, db_session.get(Payment, debit.payment_id))
    service.return_debits(db_session, batch.id, [debit.id], COLLECTION)
    assert db_session.scalar(select(func.count()).select_from(PaymentCustody)) == 1


def test_post_draft_is_atomic_with_custody(db_session, scenario, monkeypatch):
    service = scenario[0].finance
    payment = service.create_payment(db_session, scenario[1].id, COLLECTION, '100', 'receipt', 'cash').data
    def fail(db, receipt):
        record_manager_receipt(db, receipt)
        raise ValueError('synthetic_failure')
    monkeypatch.setattr('backend.services.payment_custody_service.record_manager_receipt', fail)
    assert not service.post_payment(db_session, payment.id).success
    db_session.refresh(payment)
    assert payment.lifecycle == 'draft'
    assert db_session.scalar(select(func.count()).select_from(PaymentCustody)) == 0
    monkeypatch.setattr('backend.services.payment_custody_service.record_manager_receipt', record_manager_receipt)
    assert service.post_payment(db_session, payment.id).success
    assert_manager(db_session, payment)


def test_existing_custody_never_replaced(db_session, scenario, manual):
    payment = pay(db_session, scenario, manual)
    with pytest.raises(ValueError, match='no se sustituye'):
        record_manager_receipt(db_session, payment)
    db_session.rollback()
    assert_manager(db_session, payment)
