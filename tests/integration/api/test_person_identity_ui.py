"""Identity UI and navigation, exclusively synthetic database fixtures."""
from datetime import date
from types import SimpleNamespace
import re

import pytest
from sqlalchemy import select

from backend.core.countries import COUNTRIES, COUNTRY_OPTIONS, nationality_label, nationality_options, search_key
from backend.core.booking_person_name import booking_person_links
from backend.models.person import Person
from backend.models.booking import Booking
from backend.models.booking_party import BookingParty
from tests.integration.api.test_bookings_routes import create_room


def test_retired_fields_are_absent_and_existing_values_survive_update(client, db_session):
    person = Person(full_name='Identidad sintética', birth_date=date(1990, 1, 2),
                    document_issuer_country='IT', verification_status='verified', active=True)
    db_session.add(person); db_session.commit()
    for url in ['/persons/new', f'/persons/{person.id}/edit', f'/persons/{person.id}']:
        page = client.get(url)
        assert page.status_code == 200
        for text in ['birth_date', 'document_issuer_country', 'verification_status', 'Fecha de nacimiento', 'País emisor', 'Verificación']:
            assert text not in page.text
    response = client.post(f'/persons/{person.id}/update', data={
        'full_name': person.full_name, 'nationality': 'IT', 'active': 'true',
        'birth_date': '2000-01-01', 'document_issuer_country': 'ES', 'verification_status': 'unverified',
    }, follow_redirects=False)
    assert 'success=person_saved' in response.headers['location']
    db_session.refresh(person)
    assert (person.birth_date, person.document_issuer_country, person.verification_status) == (date(1990, 1, 2), 'IT', 'verified')


@pytest.mark.parametrize('value,code,label', [('it','IT','Italia'), ('FR','FR','Francia'), ('','', '—')])
def test_nationality_roundtrip_independent_from_residence(client, db_session, value, code, label):
    result = client.post('/persons/create', data={'full_name': 'Nacionalidad sintética', 'nationality': value,
                         'country': 'ES', 'phone': '+391234567890', 'active': 'true'}, follow_redirects=False)
    assert result.status_code == 303
    person = db_session.scalar(select(Person))
    assert person.nationality == (code or None) and person.country == 'ES'
    assert label in client.get(f'/persons/{person.id}').text
    edit = client.get(f'/persons/{person.id}/edit').text
    assert re.search(r'<option value="' + code + r'"[^>]*selected', edit)
    result = client.post(f'/persons/{person.id}/update', data={'full_name': person.full_name, 'nationality': 'PL', 'country': 'ES'}, follow_redirects=False)
    assert 'success=person_saved' in result.headers['location']
    db_session.refresh(person)
    assert person.nationality == 'PL' and person.country == 'ES'
    assert 'Polonia' in client.get(f'/persons/{person.id}').text


def test_complete_local_catalogue_sorted_and_optional(client):
    assert len(COUNTRIES) == 249
    assert all(len(code) == 2 and code.isupper() for code in COUNTRIES)
    assert [search_key(label) for _, label in COUNTRY_OPTIONS] == sorted(search_key(label) for label in COUNTRIES.values())
    assert {code: COUNTRIES[code] for code in ['ES','IT','FR','RO','PL','DZ']} == {
        'ES':'España','IT':'Italia','FR':'Francia','RO':'Rumanía','PL':'Polonia','DZ':'Argelia'}
    form = client.get('/persons/new').text
    selector = form.split('name="nationality"', 1)[1].split('</select>', 1)[0]
    assert selector.count('<option') == 250
    assert 'required' not in selector.split('>', 1)[0]


def test_legacy_unknown_value_remains_readable_and_is_not_silently_erased(client, db_session):
    person = Person(full_name='Legacy sintético', nationality='ZZ', active=True)
    db_session.add(person); db_session.commit()
    assert 'Dato anterior sin normalizar: ZZ' in client.get(f'/persons/{person.id}/edit').text
    assert 'ZZ' in client.get(f'/persons/{person.id}').text
    response = client.post(f'/persons/{person.id}/update', data={'full_name': person.full_name, 'nationality': 'ZZ'}, follow_redirects=False)
    assert 'success=' in response.headers['location']
    db_session.refresh(person); assert person.nationality == 'ZZ'
    assert nationality_label('Italia') == 'Italia'
    assert nationality_options(SimpleNamespace(nationality='Italia'))[1] == 'IT'
    assert nationality_options(SimpleNamespace(nationality='Texto legado'))[1] == 'Texto legado'


def test_new_unknown_nationality_rejected(client, db_session):
    response = client.post('/persons/create', data={'full_name':'Invalid synthetic','nationality':'ZZ'}, follow_redirects=False)
    assert 'person_nationality_invalid' in response.headers['location']
    assert db_session.scalar(select(Person)) is None


def linked_booking(db):
    room = create_room(db)
    booking = Booking(room_id=room.id, origin='manual', source_guest_name='Nombre de origen sintético',
                      check_in=date(2026, 10, 1), check_out=date(2027, 8, 31))
    first, second = Person(full_name='Primera identidad sintética'), Person(full_name='Segunda identidad sintética')
    db.add_all([booking, first, second]); db.flush()
    for person, roles in [(first, ['tenant','payer','occupant']), (second, ['occupant'])]:
        db.add_all([BookingParty(booking_id=booking.id, person_id=person.id, role=role) for role in roles])
    db.commit()
    return booking, first, second


def test_booking_names_link_to_distinct_people_without_nested_modal_links(client, db_session, monkeypatch):
    monkeypatch.setattr('backend.services.booking_service.business_today', lambda: date(2026,9,20))
    booking, first, second = linked_booking(db_session)
    assert booking_person_links(booking) == [{'id':first.id,'name':first.full_name},{'id':second.id,'name':second.full_name}]
    for url in [f'/rooms/{booking.room_id}', f'/bookings/{booking.id}/finance', f'/sepa/bookings/{booking.id}']:
        page = client.get(url)
        assert page.status_code == 200
        for person in [first, second]:
            assert f'class="booking-person-link" href="/persons/{person.id}">{person.full_name}</a>' in page.text
        assert not re.search(r'<a[^>]*booking-link[^>]*>[^<]*<a', page.text)
    assert len(client.get(f'/bookings/{booking.id}/people').json()['parties']) == 4


def test_platform_name_without_person_stays_plain_text(client, db_session):
    room = create_room(db_session)
    booking = Booking(room_id=room.id, origin='ical', source_guest_name='Origen sin persona',
                      check_in=date(2026,10,1), check_out=date(2027,8,31))
    db_session.add(booking); db_session.commit()
    assert booking_person_links(booking) == []
    page = client.get(f'/bookings/{booking.id}/finance')
    assert page.status_code == 200 and 'Origen sin persona' in page.text
    assert 'class="booking-person-link"' not in page.text
    assert db_session.scalar(select(Person)) is None


def test_dashboard_and_gantt_expose_only_real_identity_links(client, db_session, monkeypatch):
    booking, first, second = linked_booking(db_session)
    booking.room.operational_since = date(2026, 1, 1)
    db_session.commit()
    monkeypatch.setattr('backend.services.dashboard_service.business_today', lambda: date(2026,9,30))
    page = client.get('/')
    assert page.status_code == 200
    assert f'href="/persons/{first.id}"' in page.text
    assert f'href="/persons/{second.id}"' in page.text
    response = client.get('/gantt/data?start=2026-09-01&end=2027-09-01')
    assert response.status_code == 200
    data = response.json()['properties'][0]['rooms'][0]['bookings'][0]
    assert data['people'] == booking_person_links(booking)
    assert all(set(person) == {'id','name'} for person in data['people'])
