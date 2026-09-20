"""Multiple functions belong to one person; all mutations use disposable test DBs."""
from datetime import date
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import event, select, text
from sqlalchemy.orm import Session

from backend.models.booking import Booking
from backend.models.booking_party import BookingParty
from backend.models.person import Person
from backend.models.booking_sepa_mandate import BookingSepaMandate
from backend.models.sepa_mandate import SepaMandate
from backend.models.sepa_creditor_profile import SepaCreditorProfile
from backend.services.booking_party_service import BookingPartyService
from tests.integration.api.test_bookings_routes import create_room, booking_data
from tests.integration.api.test_sepa_routes import _scenario, _create_profile, ES_IBAN


def manual(client, db, roles=None):
    room = create_room(db)
    payload = booking_data(room.id)
    if roles is not None:
        payload.update(initial_roles_present='true', initial_roles=roles)
    response = client.post('/bookings/create', data=payload, follow_redirects=False)
    return response, db.scalar(select(Booking))


def functions(db, booking_id, person_id):
    return {r.role: r.id for r in db.scalars(select(BookingParty).where(
        BookingParty.booking_id == booking_id, BookingParty.person_id == person_id))}


@pytest.mark.parametrize('roles', [None, ['tenant', 'occupant'], ['payer']])
def test_manual_initial_functions(client, db_session, roles):
    response, booking = manual(client, db_session, roles)
    assert response.status_code == 303
    people = list(db_session.scalars(select(Person)))
    assert len(people) == 1
    assert set(functions(db_session, booking.id, people[0].id)) == set(roles or ['tenant', 'payer', 'occupant'])


@pytest.mark.parametrize('roles', [[], ['unclassified'], ['not-a-role']])
def test_invalid_initial_functions_create_nothing(client, db_session, roles):
    response, booking = manual(client, db_session, roles)
    assert 'booking_functions_required' in response.headers['location']
    assert booking is None
    assert db_session.scalar(select(Person)) is None
    assert db_session.scalar(select(BookingParty)) is None


@pytest.mark.parametrize('before,after', [
    (['tenant', 'payer', 'occupant'], ['tenant', 'occupant']),
    (['tenant'], ['tenant', 'payer']), (['payer'], ['payer', 'occupant']),
])
def test_atomic_idempotent_edit_preserves_identity_and_booking(client, db_session, before, after):
    _, booking = manual(client, db_session, before)
    person = db_session.scalar(select(Person))
    old = functions(db_session, booking.id, person.id)
    snapshot = (booking.room_id, booking.check_in, booking.check_out, booking.source_guest_name, person.full_name)
    url = f'/bookings/{booking.id}/people/{person.id}/roles'
    for _ in range(2):
        response = client.post(url, data={'roles': after})
        assert response.status_code == 200
    new = functions(db_session, booking.id, person.id)
    assert set(new) == set(after)
    assert all(old[role] == new[role] for role in set(before) & set(after))
    db_session.refresh(booking); db_session.refresh(person)
    assert snapshot == (booking.room_id, booking.check_in, booking.check_out, booking.source_guest_name, person.full_name)
    for table in ['booking_financial_terms', 'booking_charges', 'payments', 'payment_allocations', 'sepa_batches', 'sepa_debits']:
        assert db_session.scalar(text(f'SELECT count(*) FROM {table}')) == 0


def test_add_multiple_functions_and_unlink_without_deleting_person(client, db_session):
    _, booking = manual(client, db_session, ['tenant', 'occupant'])
    parent = Person(full_name='Progenitor sintético', active=True)
    db_session.add(parent); db_session.commit()
    url = f'/bookings/{booking.id}/people'
    for roles in [['payer'], ['tenant', 'payer', 'occupant'], ['tenant', 'payer', 'occupant']]:
        assert client.post(url, data={'person_id': parent.id, 'roles': roles}).status_code == 200
    assert len(functions(db_session, booking.id, parent.id)) == 3
    response = client.post(f'{url}/{parent.id}/roles', data={})
    assert response.status_code == 422
    assert response.json()['detail'] == 'Selecciona al menos una función para el inquilino.'
    assert len(functions(db_session, booking.id, parent.id)) == 3
    for _ in range(2):
        assert client.post(f'{url}/{parent.id}/remove').status_code == 200
    assert functions(db_session, booking.id, parent.id) == {}
    assert db_session.get(Person, parent.id) is not None


def test_legacy_unclassified_survives_until_explicit_edit(client, db_session):
    room = create_room(db_session)
    person = Person(full_name='Origen sin clasificar', active=True)
    booking = Booking(room_id=room.id, origin='manual', check_in=date(2026, 9, 1), check_out=date(2026, 10, 1))
    db_session.add_all([person, booking]); db_session.flush()
    db_session.add(BookingParty(booking_id=booking.id, person_id=person.id, role='unclassified')); db_session.commit()
    response = client.get(f'/bookings/{booking.id}/people')
    assert response.json()['parties'][0]['role'] == 'unclassified'
    assert client.post(f'/bookings/{booking.id}/people/{person.id}/roles', data={'roles': ['tenant', 'occupant']}).status_code == 200
    assert set(functions(db_session, booking.id, person.id)) == {'tenant', 'occupant'}


def test_function_edit_rolls_back_every_change(db_session):
    room = create_room(db_session)
    person = Person(full_name='Rollback', active=True)
    booking = Booking(room_id=room.id, origin='manual', check_in=date(2026, 9, 1), check_out=date(2026, 10, 1))
    db_session.add_all([person, booking]); db_session.flush()
    db_session.add(BookingParty(booking_id=booking.id, person_id=person.id, role='tenant')); db_session.commit()
    booking_id, person_id = booking.id, person.id
    original = functions(db_session, booking_id, person_id)
    def fail_after_sql(*args):
        raise RuntimeError('Synthetic failure after flush')
    event.listen(db_session, 'after_flush_postexec', fail_after_sql)
    try:
        with pytest.raises(RuntimeError):
            BookingPartyService().change_functions(db_session, booking_id, person_id, ['payer'])
    finally:
        event.remove(db_session, 'after_flush_postexec', fail_after_sql)
    assert functions(db_session, booking_id, person_id) == original


def test_concurrent_add_does_not_duplicate(db_session):
    room = create_room(db_session)
    person = Person(full_name='Concurrencia', active=True)
    booking = Booking(room_id=room.id, origin='manual', check_in=date(2026, 9, 1), check_out=date(2026, 10, 1))
    db_session.add_all([person, booking]); db_session.commit()
    booking_id, person_id, engine = booking.id, person.id, db_session.get_bind()
    db_session.rollback()
    def add(_):
        with Session(engine) as session:
            return BookingPartyService().change_functions(session, booking_id, person_id, ['tenant', 'payer', 'occupant'], mode='add')
    with ThreadPoolExecutor(max_workers=2) as executor:
        assert len(list(executor.map(add, range(2)))) == 2
    assert len(functions(db_session, booking_id, person_id)) == 3


@pytest.mark.parametrize('action', ['roles', 'remove'])
def test_sepa_requires_explicit_review_without_changing_mandate(client, db_session, action):
    owner, _, account, _, booking, person, _ = _scenario(db_session)
    _create_profile(client, owner, account)
    profile = db_session.scalar(select(SepaCreditorProfile))
    mandate = SepaMandate(creditor_profile_id=profile.id, person_id=person.id, debtor_name='Deudor sintético',
                         debtor_iban=ES_IBAN, debtor_bic='CAIXESBBXXX', mandate_reference='TEST-FUNCTIONS',
                         signature_date=date(2026, 9, 1), status='active')
    db_session.add(mandate); db_session.flush()
    binding = BookingSepaMandate(booking_id=booking.id, mandate_id=mandate.id, active=True)
    db_session.add(binding); db_session.commit()
    original = (mandate.debtor_iban, mandate.person_id, mandate.mandate_reference, mandate.status)
    payer_id = functions(db_session, booking.id, person.id)['payer']
    assert client.post(f'/bookings/{booking.id}/parties/{payer_id}/remove').status_code == 422
    url = f'/bookings/{booking.id}/people/{person.id}/{action}'
    data = {'roles': ['tenant']}
    assert client.post(url, data=data).status_code == 409
    assert 'payer' in functions(db_session, booking.id, person.id)
    response = client.post(url, data=dict(data, confirm_sepa_review='true'))
    assert response.status_code == 200 and response.json()['warning']
    db_session.refresh(mandate); db_session.refresh(binding)
    assert original == (mandate.debtor_iban, mandate.person_id, mandate.mandate_reference, mandate.status)
    assert binding.active


def test_manual_template_has_three_checked_defaults_and_multi_add(client, db_session):
    import re
    room = create_room(db_session)
    document = client.get(f'/rooms/{room.id}').text
    initial = document.split('id="bookingInitialFunctions"', 1)[1].split('</fieldset>', 1)[0]
    assert set(re.findall(r'value="([a-z]+)" checked', initial)) == {'tenant', 'payer', 'occupant'}
    assert 'id="bookingPartyRole"' not in document
    additional = document.split('id="bookingPartyFunctions"', 1)[1].split('</fieldset>', 1)[0]
    assert additional.count('type="checkbox"') == 4


def test_three_functions_are_one_sepa_payer_and_finance_uses_current_roles(client, db_session):
    owner, _, account, _, booking, person, _ = _scenario(db_session)
    _create_profile(client, owner, account)
    BookingPartyService().change_functions(db_session, booking.id, person.id, ['tenant', 'payer', 'occupant'])
    page = client.get(f'/sepa/bookings/{booking.id}')
    selector = page.text.split('name="person_id"', 1)[1].split('</select>', 1)[0]
    assert selector.count(f'value="{person.id}" selected') == 1
    assert 'Hay varios responsables de pago' not in page.text
    finance = client.get(f'/bookings/{booking.id}/finance')
    assert 'No hay responsable de pago clasificado' not in finance.text
    BookingPartyService().change_functions(db_session, booking.id, person.id, ['tenant', 'occupant'])
    assert 'No hay responsable de pago clasificado para esta reserva.' in client.get(f'/bookings/{booking.id}/finance').text


def test_function_change_writes_only_booking_parties(client, db_session):
    _, booking = manual(client, db_session)
    person = db_session.scalar(select(Person))
    statements = []
    def capture(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith(('INSERT ', 'UPDATE ', 'DELETE ')):
            statements.append(statement.lower())
    engine = db_session.get_bind()
    event.listen(engine, 'before_cursor_execute', capture)
    try:
        BookingPartyService().change_functions(db_session, booking.id, person.id, ['tenant', 'guarantor'])
    finally:
        event.remove(engine, 'before_cursor_execute', capture)
    assert statements
    assert all('booking_parties' in statement for statement in statements)
