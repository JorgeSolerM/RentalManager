from datetime import date
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from backend.core.bbva_sepa import validate_structure
from backend.models.booking_sepa_mandate import BookingSepaMandate
from backend.models.booking_charge import BookingCharge
from backend.models.booking import Booking
from backend.models.payment import Payment
from backend.models.payment_allocation import PaymentAllocation
from backend.models.sepa_collection import SepaBatch, SepaDebit, SepaDebitChargeAllocation, SepaExportArtifact
from backend.models.sepa_creditor_profile import SepaCreditorProfile
from backend.models.sepa_mandate import SepaMandate
from backend.services.financial_service import FinancialService
from backend.services.sepa_collection_service import SepaCollectionService
from tests.integration.api.test_sepa_routes import _scenario, ES_IBAN, GB_IBAN

PERIOD = date(2026, 9, 1)
COLLECTION = date(2026, 9, 10)


@pytest.fixture
def scenario(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr('backend.services.sepa_collection_service.business_today', lambda: COLLECTION)
    monkeypatch.setattr('backend.api.routers.collections.business_today', lambda: COLLECTION)
    owner, _, account, _, booking, person, _ = _scenario(db_session)
    account.bic = "TESTESMMXXX"
    profile = SepaCreditorProfile(display_name="Perfil pruebas", creditor_name="Acreedor pruebas",
        creditor_identifier="ES12ZZZ12345678", bank_account_id=account.id, owner_id=owner.id, scheme="CORE", active=True)
    db_session.add(profile); db_session.flush()
    mandate = SepaMandate(creditor_profile_id=profile.id, person_id=person.id, debtor_name="Deudor pruebas",
        debtor_iban=GB_IBAN, debtor_bic="TESTGBMMXXX", mandate_reference="TEST-MANDATE", signature_date=PERIOD,
        mandate_type="RCUR", status="active")
    db_session.add(mandate); db_session.flush()
    db_session.add(BookingSepaMandate(booking_id=booking.id, mandate_id=mandate.id, active=True)); db_session.commit()
    service = SepaCollectionService(tmp_path / 'private_xml')
    monkeypatch.setattr('backend.api.routers.collections.service', service)
    service.save_settings(db_session, "Presentador de pruebas", "TEST-INITIATOR")
    finance = FinancialService()
    charges = []
    for kind, amount in (("rent", "400.00"), ("security_deposit", "400.00"), ("utilities", "25.30")):
        charge = finance.create_charge(db_session, booking.id, kind, "Alquiler & gastos ñ " + kind, PERIOD, amount).data
        finance.post_charge(db_session, charge.id)
        charges.append(charge)
    return service, booking, profile, mandate, charges


def create(db, scenario, ids=None, key=None):
    service, booking, _, _, charges = scenario
    return service.create(db, PERIOD, [booking.room.property_id], COLLECTION,
                          ids if ids is not None else [c.id for c in charges], key or str(uuid4()))


def count(db, model):
    return db.scalar(select(func.count()).select_from(model))


def test_full_flow_grouped_charges_artifact_and_idempotent_collection(db_session, scenario):
    service, booking, _, _, charges = scenario
    key = str(uuid4())
    batch = create(db_session, scenario, key=key)
    assert create(db_session, scenario, key=key).id == batch.id
    assert count(db_session, SepaDebit) == 1
    assert count(db_session, SepaDebitChargeAllocation) == 3
    debit = db_session.scalar(select(SepaDebit))
    assert debit.amount == Decimal('825.30')
    assert len(debit.end_to_end_id) <= 35
    service.export(db_session, batch.id)
    assert count(db_session, Payment) == 0
    artifact = db_session.scalar(select(SepaExportArtifact))
    content = service.artifact_path(db_session, artifact.id).read_bytes()
    validate_structure(content)
    assert sha256(content).hexdigest() == artifact.sha256
    assert b'pain.008.001.02' in content and b'CORE' in content and b'RCUR' in content
    assert GB_IBAN.encode() in content and b'TESTGBMMXXX' in content
    service.export(db_session, batch.id)
    assert count(db_session, SepaExportArtifact) == 1
    service.present(db_session, batch.id)
    assert count(db_session, Payment) == 0
    service.collect(db_session, batch.id, [debit.id], COLLECTION)
    service.collect(db_session, batch.id, [debit.id], COLLECTION)
    assert count(db_session, Payment) == 1 and count(db_session, PaymentAllocation) == 3
    assert service.get_batch(db_session, batch.id).status == 'collected'
    assert all(service.finance.charge_balance(db_session, c.id).outstanding_amount == 0 for c in charges)


def test_global_initiator_persists_and_batch_keeps_its_snapshot(db_session, scenario):
    from xml.etree import ElementTree as ET
    from backend.core.bbva_sepa import NS
    service, _, profile, _, _ = scenario
    creditor_name = profile.creditor_name
    service.save_settings(db_session, 'Iniciador sintetico', 'TEST-INIT-ONE')
    db_session.expire_all()
    assert service.settings(db_session).initiator_name == 'Iniciador sintetico'
    batch = create(db_session, scenario)
    service.save_settings(db_session, 'Otro iniciador sintetico', 'TEST-INIT-TWO')
    service.export(db_session, batch.id)
    artifact = db_session.scalar(select(SepaExportArtifact))
    root = ET.fromstring(service.artifact_path(db_session, artifact.id).read_bytes())
    ns = {'s': NS}
    assert root.findtext('.//s:InitgPty/s:Nm', namespaces=ns) == 'Iniciador sintetico'
    assert root.findtext('.//s:InitgPty/s:Id/s:PrvtId/s:Othr/s:Id', namespaces=ns) == 'TEST-INIT-ONE'
    assert root.findtext('.//s:Cdtr/s:Nm', namespaces=ns) == creditor_name
    assert service.settings(db_session).initiator_identifier == 'TEST-INIT-TWO'


def test_generated_xml_has_complete_bbva_core_fields(db_session, scenario):
    from xml.etree import ElementTree as ET
    from datetime import datetime
    from backend.core.bbva_sepa import NS
    service = scenario[0]
    batch = create(db_session, scenario)
    service.export(db_session, batch.id)
    artifact = db_session.scalar(select(SepaExportArtifact))
    root = ET.fromstring(service.artifact_path(db_session, artifact.id).read_bytes())
    ns = {'s': NS}
    def value(path):
        result = root.findtext('.//' + '/'.join('s:' + part for part in path.split('/')), namespaces=ns)
        assert result
        return result
    assert root.tag == '{' + NS + '}Document'
    assert len(value('GrpHdr/MsgId')) <= 35
    datetime.fromisoformat(value('GrpHdr/CreDtTm'))
    for path in ('GrpHdr/NbOfTxs', 'GrpHdr/CtrlSum', 'InitgPty/Nm', 'InitgPty/Id/PrvtId/Othr/Id',
                 'PmtInf/PmtInfId', 'Cdtr/Nm', 'CdtrAcct/Id/IBAN', 'CdtrAgt/FinInstnId/BIC',
                 'CdtrSchmeId/Id/PrvtId/Othr/Id', 'PmtId/EndToEndId', 'MndtRltdInf/MndtId',
                 'Dbtr/Nm', 'DbtrAcct/Id/IBAN', 'DbtrAgt/FinInstnId/BIC', 'RmtInf/Ustrd'):
        value(path)
    assert value('PmtInf/PmtMtd') == 'DD'
    assert value('PmtInf/BtchBookg') == 'true'
    assert value('SvcLvl/Cd') == 'SEPA'
    assert value('LclInstrm/Cd') == 'CORE'
    assert value('PmtTpInf/SeqTp') == 'RCUR'
    assert value('MndtRltdInf/AmdmntInd') == 'false'
    date.fromisoformat(value('PmtInf/ReqdColltnDt'))
    date.fromisoformat(value('MndtRltdInf/DtOfSgntr'))
    assert root.find('.//s:InstdAmt', ns).attrib == {'Ccy': 'EUR'}
    assert count(db_session, Payment) == 0


def test_preview_period_types_balance_and_reserved(db_session, scenario):
    service, booking, _, _, charges = scenario
    finance = service.finance
    finance.create_charge(db_session, booking.id, 'rent', 'Draft', PERIOD, 500)
    credit = finance.create_charge(db_session, booking.id, 'discount', 'Descuento', PERIOD, 5).data
    finance.post_charge(db_session, credit.id)
    other = finance.create_charge(db_session, booking.id, 'rent', 'Octubre', date(2026,10,1), 400).data
    finance.post_charge(db_session, other.id)
    payment = finance.create_payment(db_session, booking.id, PERIOD, 100, 'receipt', 'cash').data
    finance.post_payment(db_session, payment.id)
    finance.allocate(db_session, payment.id, charges[0].id, 100)
    rows = service.preview(db_session, PERIOD, [booking.room.property_id], COLLECTION)
    assert len(rows) == 3 and rows[0]['amount'] == Decimal('300.00')
    assert service.preview(db_session, PERIOD, [99999], COLLECTION) == []
    create(db_session, scenario)
    assert all(not r['eligible'] and 'otra remesa' in r['reason'] for r in service.preview(db_session, PERIOD, [booking.room.property_id], COLLECTION))
    with pytest.raises(ValueError): create(db_session, scenario)


@pytest.mark.parametrize('change,reason', [('inactive','Mandato inactivo'),('bic','BIC'),('missing','Falta mandato'),('amended','modificado'),('future','firma')])
def test_ineligible_mandates_explained(db_session, scenario, change, reason):
    service, booking, _, mandate, _ = scenario
    if change == 'inactive': mandate.status = 'cancelled'
    if change == 'bic': mandate.debtor_bic = None
    if change == 'amended': mandate.amendment_indicator = True
    if change == 'future': mandate.signature_date = date(2027,1,1)
    if change == 'missing': db_session.scalar(select(BookingSepaMandate)).active = False
    db_session.commit(); db_session.expire_all()
    rows = service.preview(db_session, PERIOD, [booking.room.property_id], COLLECTION)
    assert all(not r['eligible'] and reason in r['reason'] for r in rows)


def test_collection_rolls_back_after_late_allocation_error(db_session, scenario, monkeypatch):
    service, _, _, _, _ = scenario
    batch = create(db_session, scenario); service.export(db_session, batch.id); service.present(db_session, batch.id)
    debit = db_session.scalar(select(SepaDebit))
    original = db_session.add
    def fail(obj, *args, **kwargs):
        if isinstance(obj, PaymentAllocation): raise RuntimeError('Simulated failure')
        return original(obj, *args, **kwargs)
    monkeypatch.setattr(db_session, 'add', fail)
    with pytest.raises(RuntimeError): service.collect(db_session, batch.id, [debit.id], COLLECTION)
    assert count(db_session, Payment) == 0 and count(db_session, PaymentAllocation) == 0
    assert db_session.get(SepaDebit, debit.id).payment_id is None


def test_export_revalidates_bank_and_charge_changes(db_session, scenario):
    service, _, _, mandate, charges = scenario
    batch = create(db_session, scenario)
    mandate.debtor_name = 'Nombre cambiado'; db_session.commit()
    with pytest.raises(ValueError, match='bancarios'): service.export(db_session, batch.id)
    assert count(db_session, SepaExportArtifact) == 0 and count(db_session, Payment) == 0
    mandate.debtor_name = 'Deudor pruebas'; db_session.commit()
    service.finance.void_charge(db_session, charges[0].id, 'Prueba')
    with pytest.raises(ValueError, match='cargo'): service.export(db_session, batch.id)


def test_routes_preview_empty_masking_and_download(client, db_session, scenario):
    service, booking, _, _, _ = scenario
    assert client.get('/collections').status_code == 200
    assert client.get('/collections/new').status_code == 200
    data = {'period':'2026-09', 'collection_date':'2026-09-10', 'property_ids':booking.room.property_id}
    response = client.post('/collections/preview', data=data)
    assert response.status_code == 200 and 'Listo' in response.text
    assert GB_IBAN not in response.text and ES_IBAN not in response.text
    assert 'name="charge_ids"' in response.text
    response = client.post('/collections/preview', data={**data, 'period':'2026-11'})
    assert 'No hay cargos contabilizados para este periodo.' in response.text
    batch = create(db_session, scenario)
    service.export(db_session, batch.id)
    response = client.get(f'/collections/{batch.id}')
    assert response.status_code == 200 and GB_IBAN not in response.text
    artifact = db_session.scalar(select(SepaExportArtifact))
    response = client.get(f'/collections/artifacts/{artifact.id}')
    assert response.status_code == 200 and 'no-store' in response.headers['cache-control']
    assert 'attachment' in response.headers['content-disposition']
    assert client.post('/collections/create', data={'period':'malformed'}).status_code == 400


def add_second_booking(db, scenario, *, other_creditor=False):
    from backend.models.owner_bank_account import OwnerBankAccount
    from backend.models.property import Property
    from backend.models.property_ownership import PropertyOwnership
    from backend.models.room import Room
    service, first, profile, mandate, _ = scenario
    room_id = first.room_id
    if other_creditor:
        account = db.scalar(select(OwnerBankAccount).where(OwnerBankAccount.id != profile.bank_account_id))
        account.bic = 'TESTGBMMXXX'
        finca = Property(name='Segunda finca', address='Ejemplo 2', street='Ejemplo', city='Elche', owner='')
        db.add(finca); db.flush()
        db.add(PropertyOwnership(property_id=finca.id, owner_id=account.owner_id, rent_bank_account_id=account.id, ownership_percentage=100, active=True))
        room = Room(property_id=finca.id, code='T02', active=True)
        db.add(room); db.flush(); room_id = room.id
        profile = SepaCreditorProfile(display_name='Otro perfil', creditor_name='Segundo acreedor', creditor_identifier='ES12ZZZ87654321', bank_account_id=account.id, owner_id=account.owner_id, scheme='CORE', active=True)
        db.add(profile); db.flush()
        mandate = SepaMandate(creditor_profile_id=profile.id, debtor_name='Otro deudor', debtor_iban=ES_IBAN, debtor_bic='TESTESMMXXX', mandate_reference='TEST-SECOND', signature_date=PERIOD, mandate_type='RCUR', status='active')
        db.add(mandate); db.flush()
    booking = Booking(room_id=room_id, origin='manual', check_in=PERIOD, check_out=date(2027,1,1))
    db.add(booking); db.flush()
    db.add(BookingSepaMandate(booking_id=booking.id, mandate_id=mandate.id, active=True)); db.commit()
    charge = service.finance.create_charge(db, booking.id, 'rent', 'Alquiler segundo', PERIOD, 200).data
    service.finance.post_charge(db, charge.id)
    return booking, charge


@pytest.mark.parametrize('other_creditor', [False, True])
def test_multiple_debits_groups_partial_and_complete_collection(db_session, scenario, other_creditor):
    service, booking, _, _, charges = scenario
    second, charge = add_second_booking(db_session, scenario, other_creditor=other_creditor)
    batch = service.create(db_session, PERIOD, [booking.room.property_id, second.room.property_id], COLLECTION,
                           [c.id for c in charges] + [charge.id], str(uuid4()))
    batch = service.get_batch(db_session, batch.id)
    assert len(batch.groups) == (2 if other_creditor else 1)
    service.export(db_session, batch.id)
    assert count(db_session, SepaExportArtifact) == (2 if other_creditor else 1)
    service.present(db_session, batch.id)
    ids = list(db_session.scalars(select(SepaDebit.id).order_by(SepaDebit.id)))
    service.collect(db_session, batch.id, ids[:1], COLLECTION)
    assert count(db_session, Payment) == 1
    assert service.get_batch(db_session, batch.id).status == 'partially_collected'
    service.collect(db_session, batch.id, ids, COLLECTION)
    assert count(db_session, Payment) == 2
    assert service.get_batch(db_session, batch.id).status == 'collected'
    assert count(db_session, PaymentAllocation) == 4


def test_collection_rejects_other_batch_and_stale_balance(db_session, scenario):
    service, booking, _, _, charges = scenario
    batch = create(db_session, scenario); service.export(db_session, batch.id); service.present(db_session, batch.id)
    debit = db_session.scalar(select(SepaDebit))
    with pytest.raises(ValueError): service.collect(db_session, batch.id, [debit.id,999], COLLECTION)
    payment = service.finance.create_payment(db_session, booking.id, PERIOD, 10, 'receipt', 'cash').data
    service.finance.post_payment(db_session, payment.id)
    service.finance.allocate(db_session, payment.id, charges[0].id, 10)
    with pytest.raises(ValueError): service.collect(db_session, batch.id, [debit.id], COLLECTION)
    assert count(db_session, Payment) == 1 and db_session.get(SepaDebit,debit.id).payment_id is None


def test_ooff_cannot_be_reused(db_session, scenario):
    service, booking, _, mandate, charges = scenario
    mandate.mandate_type = 'OOFF'; db_session.commit()
    batch = create(db_session, scenario, ids=[charges[0].id]); service.export(db_session,batch.id)
    artifact = db_session.scalar(select(SepaExportArtifact))
    assert b'<SeqTp>OOFF</SeqTp>' in service.artifact_path(db_session,artifact.id).read_bytes()
    rows = service.preview(db_session,PERIOD,[booking.room.property_id],COLLECTION)
    assert all(not r['eligible'] for r in rows)


def test_concurrent_batch_and_payment_idempotence(db_session, scenario):
    from concurrent.futures import ThreadPoolExecutor
    from sqlalchemy.orm import Session
    service, booking, _, _, charges = scenario
    engine = db_session.get_bind()
    property_id, ids, key = booking.room.property_id, [c.id for c in charges], str(uuid4())
    db_session.rollback()
    def create_once(_):
        with Session(engine, autoflush=False) as session:
            return service.create(session,PERIOD,[property_id],COLLECTION,ids,key).id
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(create_once,range(2)))
    assert len(set(results)) == 1
    batch_id = results[0]
    service.export(db_session,batch_id); service.present(db_session,batch_id)
    debit_ids = list(db_session.scalars(select(SepaDebit.id))); db_session.rollback()
    def collect_once(_):
        with Session(engine,autoflush=False) as session:
            return service.collect(session,batch_id,debit_ids,COLLECTION).status
    with ThreadPoolExecutor(max_workers=2) as executor:
        assert list(executor.map(collect_once,range(2))) == ['collected','collected']
    assert count(db_session,Payment) == 1


def test_artifact_tampering_refuses_download(db_session,scenario):
    service, *_ = scenario
    batch=create(db_session,scenario); service.export(db_session,batch.id)
    artifact=db_session.scalar(select(SepaExportArtifact))
    # Corrupt only the temporary test artifact, never a production export.
    service.artifact_path(db_session,artifact.id).write_bytes(b'corrupt')
    with pytest.raises(ValueError,match='integridad'): service.artifact_path(db_session,artifact.id)


def test_public_app_cannot_access_collections_or_private_files(db_session, scenario):
    from fastapi.testclient import TestClient
    from backend.public.app_factory import create_public_app
    from backend.database.session import get_db
    service, *_ = scenario
    batch = create(db_session,scenario); service.export(db_session,batch.id)
    app = create_public_app()
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as public:
        for path in ('/collections','/collections/1','/collections/artifacts/1','/data/finance/sepa/','/static/../data/sepa_reference/private.xml'):
            response = public.get(path)
            assert response.status_code == 404
            assert GB_IBAN not in response.text and ES_IBAN not in response.text


def test_ambiguity_missing_account_and_creditor_explained(db_session,scenario):
    from backend.models.owner_bank_account import OwnerBankAccount
    from backend.models.property_ownership import PropertyOwnership
    service, booking, profile, _, _ = scenario
    account = db_session.scalar(select(OwnerBankAccount).where(OwnerBankAccount.id != profile.bank_account_id))
    second = SepaCreditorProfile(display_name='Otra posibilidad', creditor_name='Otro acreedor',creditor_identifier='ES12ZZZ87654321',bank_account_id=account.id,owner_id=account.owner_id,scheme='CORE',active=True)
    db_session.add(second)
    db_session.add(PropertyOwnership(property_id=booking.room.property_id,owner_id=account.owner_id,rent_bank_account_id=account.id,ownership_percentage=1,active=True))
    binding = db_session.scalar(select(BookingSepaMandate)); binding.active=False
    db_session.commit(); db_session.expire_all()
    assert all(r['reason']=='Acreedor ambiguo' for r in service.preview(db_session,PERIOD,[booking.room.property_id],COLLECTION))
    profile.active=False; second.active=False; db_session.commit()
    assert all(r['reason']=='Falta acreedor' for r in service.preview(db_session,PERIOD,[booking.room.property_id],COLLECTION))
    for account in db_session.scalars(select(OwnerBankAccount)): account.active=False
    db_session.commit()
    assert all(r['reason']=='Falta cuenta receptora' for r in service.preview(db_session,PERIOD,[booking.room.property_id],COLLECTION))


def test_fixture_coverage_and_synthetic_values():
    import xml.etree.ElementTree as ET
    from backend.core.bbva_sepa import N
    from backend.core.iban import is_valid_iban
    roots=[ET.parse(p).getroot() for p in sorted(Path('tests/fixtures/sepa_bbva').glob('*.xml'))]
    assert [len(r.findall('.//s:DrctDbtTxInf',N)) for r in roots] == [10,3,1,2,2,3,7]
    assert {e.text[:2] for r in roots for e in r.findall('.//s:IBAN',N)} >= {'ES','DE','NL','LT','FR','PT'}
    assert all(is_valid_iban(e.text) for r in roots for e in r.findall('.//s:IBAN',N))
    assert all(e.text.startswith('TEST') for r in roots for e in r.findall('.//s:BIC',N))
    assert all(e.text.startswith('SUJETO SINTETICO ') for r in roots for e in r.findall('.//s:Nm',N))
    assert len({r.find('.//s:InitgPty/s:Id/s:PrvtId/s:Othr/s:Id',N).text for r in roots}) == 1
    assert len({r.find('.//s:CdtrAcct/s:Id/s:IBAN',N).text for r in roots}) == 3
    concepts={e.text for r in roots for e in r.findall('.//s:Ustrd',N)}
    assert any('SUMINISTROS' in t for t in concepts) and any('FIANZA' in t for t in concepts)


@pytest.mark.parametrize('file', sorted(Path('tests/fixtures/sepa_bbva').glob('*.xml')), ids=lambda p: p.stem)
def test_anonymized_bbva_reference_structure(file):
    validate_structure(file.read_bytes())
