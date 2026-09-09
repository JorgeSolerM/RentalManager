from concurrent.futures import ThreadPoolExecutor
from datetime import date

import re
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.sepa_creditor_profile import SepaCreditorProfile
from backend.models.sepa_mandate import SepaMandate
from backend.models.property_ownership import PropertyOwnership
from backend.services.sepa_service import SepaService
from tests.integration.api.test_sepa_routes import _scenario, _create_profile, ES_IBAN


def selected(html, name):
    content = re.search(r'<select[^>]*name="' + name + r'"[^>]*>(.*?)</select>', html, re.S).group(1)
    return re.search(r'<option value="([^"]*)" selected', content).group(1)


def test_sequence_independent_concurrent_and_no_mandates(client, db_session):
    owner, other, account, foreign, *_ = _scenario(db_session)
    _create_profile(client, owner, account)
    _create_profile(client, other, foreign)
    ids = list(db_session.scalars(select(SepaCreditorProfile.id).order_by(SepaCreditorProfile.id)))
    assert client.post('/sepa/references', data={'creditor_profile_id': ids[0]}).json()['reference'] == 'HSI000000001'
    assert client.post('/sepa/references', data={'creditor_profile_id': ids[1]}).json()['reference'] == 'HSI000000001'
    engine = db_session.get_bind()
    def generate(_):
        with Session(engine) as session:
            return SepaService().generate_reference(session, ids[0]).data
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(generate, range(12)))
    assert sorted(results) == [f'HSI{n:09d}' for n in range(2, 14)]
    assert all(len(value) <= 35 for value in results)
    assert db_session.scalar(select(SepaMandate.id)) is None


def test_existing_reference_skipped_and_limit(client, db_session):
    owner, _, account, _, _, person, _ = _scenario(db_session)
    _create_profile(client, owner, account)
    profile = db_session.scalar(select(SepaCreditorProfile))
    db_session.add(SepaMandate(creditor_profile_id=profile.id, debtor_name='Test', debtor_iban=ES_IBAN,
        mandate_reference='HSI000000001', signature_date=date(2026, 1, 1), status='draft'))
    db_session.commit()
    assert SepaService().generate_reference(db_session, profile.id).data == 'HSI000000002'
    profile.mandate_reference_counter = 999999999
    db_session.commit()
    assert not SepaService().generate_reference(db_session, profile.id).success


def test_draft_editable_active_protected(client, db_session):
    owner, _, account, _, _, person, _ = _scenario(db_session)
    _create_profile(client, owner, account)
    profile = db_session.scalar(select(SepaCreditorProfile))
    data = dict(creditor_profile_id=profile.id, debtor_name='Test', debtor_iban=ES_IBAN,
                mandate_reference='HSI000000001', signature_date='2026-01-01', status='draft')
    url = f'/sepa/persons/{person.id}/mandates'
    client.post(url, data=data)
    mandate = db_session.scalar(select(SepaMandate))
    data.update(mandate_reference='MANUAL', status='active')
    client.post(f'{url}/{mandate.id}', data=data)
    db_session.refresh(mandate)
    assert mandate.mandate_reference == 'MANUAL'
    data.update(mandate_reference='CHANGED')
    response = client.post(f'{url}/{mandate.id}', data=data, follow_redirects=False)
    assert 'sepa_reference_immutable' in response.headers['location']
    db_session.refresh(mandate)
    assert mandate.mandate_reference == 'MANUAL'
    assert 'sepa_mandate_reference_exists' in client.post(url, data=dict(data, mandate_reference='MANUAL'), follow_redirects=False).headers['location']


def test_ui_creation_and_booking_selection(client, db_session):
    owner, other, account, foreign, booking, person, _ = _scenario(db_session)
    _create_profile(client, owner, account)
    profile = db_session.scalar(select(SepaCreditorProfile))
    page = client.get(f'/sepa/bookings/{booking.id}').text
    assert selected(page, 'creditor_profile_id') == str(profile.id)
    assert selected(page, 'person_id') == str(person.id)
    _create_profile(client, other, foreign)
    db_session.add(PropertyOwnership(property_id=booking.room.property_id, owner_id=other.id,
        rent_bank_account_id=foreign.id, ownership_percentage=50, active=True))
    db_session.commit()
    page = client.get(f'/sepa/bookings/{booking.id}').text
    assert selected(page, 'creditor_profile_id') == ''
    created = client.post('/persons/create', data={'full_name':'Nuevo Test'}, follow_redirects=False)
    detail = client.get(created.headers['location'])
    assert 'Crear mandato SEPA' in detail.text and 'id="new-sepa-mandate"' in detail.text
    assert 'Generar referencia' in detail.text
    assert db_session.scalar(select(SepaMandate.id)) is None
