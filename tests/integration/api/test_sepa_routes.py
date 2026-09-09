from datetime import date

from sqlalchemy import select

from backend.models.booking import Booking
from backend.models.booking_party import BookingParty
from backend.models.owner import Owner
from backend.models.owner_bank_account import OwnerBankAccount
from backend.models.person import Person
from backend.models.property import Property
from backend.models.property_ownership import PropertyOwnership
from backend.models.room import Room
from backend.models.sepa_creditor_profile import SepaCreditorProfile
from backend.models.sepa_mandate import SepaMandate


ES_IBAN = "ES9121000418450200051332"
GB_IBAN = "GB82WEST12345698765432"


def _scenario(db):
    owner = Owner(legal_name="Titular", active=True)
    other_owner = Owner(legal_name="Otro", active=True)
    property_obj = Property(name="Finca", address="Calle 1", street="Calle", city="Elche", owner="", active=True)
    db.add_all([owner, other_owner, property_obj]); db.flush()
    account = OwnerBankAccount(owner_id=owner.id, account_holder_name="Titular", iban=ES_IBAN,
                               active=True, receives_rent=True)
    foreign_account = OwnerBankAccount(owner_id=other_owner.id, account_holder_name="Otro", iban=GB_IBAN,
                                       active=True, receives_rent=True)
    db.add_all([account, foreign_account]); db.flush()
    db.add(PropertyOwnership(property_id=property_obj.id, owner_id=owner.id,
                             ownership_percentage=100, rent_bank_account_id=account.id, active=True))
    room = Room(property_id=property_obj.id, code="T01", active=True)
    person = Person(full_name="Pagador Uno", iban=GB_IBAN, active=True)
    second_person = Person(full_name="Pagador Dos", active=True)
    db.add_all([room, person, second_person]); db.flush()
    booking = Booking(room_id=room.id, origin="manual", check_in=date(2026, 9, 1),
                      check_out=date(2027, 6, 30))
    db.add(booking); db.flush()
    db.add(BookingParty(booking_id=booking.id, person_id=person.id, role="payer")); db.commit()
    return owner, other_owner, account, foreign_account, booking, person, second_person


def _create_profile(client, owner, account, **overrides):
    data = {"display_name": "Cobros finca", "creditor_name": "Acreedor Real",
            "creditor_identifier": "es 12 zzz 12345678", "bank_account_id": str(account.id),
            "scheme": "CORE", "active": "true"}
    data.update(overrides)
    return client.post(f"/sepa/owners/{owner.id}/profiles", data=data, follow_redirects=False)


def test_creditor_profile_validates_owner_account_eligibility_and_identifier(client, db_session):
    owner, _, account, foreign, *_ = _scenario(db_session)
    response = _create_profile(client, owner, account)
    assert response.status_code == 303
    profile = db_session.scalar(select(SepaCreditorProfile))
    assert profile.creditor_identifier == "ES12ZZZ12345678"
    assert profile.scheme == "CORE"
    duplicate_active = _create_profile(client, owner, account, display_name="Segundo perfil")
    assert "sepa_profile_account_conflict" in duplicate_active.headers["location"]
    updated = client.post(
        f"/sepa/owners/{owner.id}/profiles/{profile.id}",
        data={"display_name": "Cobros actualizados", "creditor_name": "Acreedor Real",
              "creditor_identifier": "ES12ZZZ12345678", "bank_account_id": account.id,
              "scheme": "CORE", "active": "true"},
        follow_redirects=False,
    )
    db_session.refresh(profile)
    assert updated.status_code == 303 and profile.display_name == "Cobros actualizados"

    wrong = _create_profile(client, owner, foreign, display_name="Incorrecto")
    assert "sepa_account_wrong_owner" in wrong.headers["location"]
    invalid = _create_profile(client, owner, account, creditor_identifier="NIF")
    assert "sepa_creditor_identifier_invalid" in invalid.headers["location"]
    account.receives_rent = False; db_session.commit()
    ineligible = _create_profile(client, owner, account)
    assert "sepa_account_not_eligible" in ineligible.headers["location"]


def test_mandate_is_independent_from_person_and_reference_unique_per_creditor(client, db_session):
    owner, _, account, _, _, person, _ = _scenario(db_session)
    _create_profile(client, owner, account)
    profile = db_session.scalar(select(SepaCreditorProfile))
    data = {"creditor_profile_id": profile.id, "debtor_name": "Titular Bancario",
            "debtor_iban": "es91 2100 0418 4502 0005 1332", "debtor_bic": "caixesbbxxx",
            "mandate_reference": "MANDATO-001", "signature_date": "2026-09-01",
            "mandate_type": "RCUR", "status": "draft"}
    created = client.post(f"/sepa/persons/{person.id}/mandates", data=data, follow_redirects=False)
    assert created.status_code == 303
    mandate = db_session.scalar(select(SepaMandate))
    assert mandate.debtor_name == "Titular Bancario"
    assert mandate.debtor_iban == ES_IBAN
    assert mandate.debtor_bic == "CAIXESBBXXX"
    person.iban = GB_IBAN; db_session.commit(); db_session.refresh(mandate)
    assert mandate.debtor_iban == ES_IBAN

    duplicate = client.post(f"/sepa/persons/{person.id}/mandates", data=data, follow_redirects=False)
    assert "sepa_mandate_reference_exists" in duplicate.headers["location"]
    invalid = dict(data, mandate_reference="MANDATO-002", debtor_iban="ES001")
    rejected = client.post(f"/sepa/persons/{person.id}/mandates", data=invalid, follow_redirects=False)
    assert "sepa_debtor_iban_invalid" in rejected.headers["location"]
    invalid_bic = dict(data, mandate_reference="MANDATO-003", debtor_bic="BIC-MALO")
    rejected_bic = client.post(f"/sepa/persons/{person.id}/mandates", data=invalid_bic, follow_redirects=False)
    assert "sepa_debtor_bic_invalid" in rejected_bic.headers["location"]
    cancelled = dict(data, status="cancelled")
    updated = client.post(f"/sepa/persons/{person.id}/mandates/{mandate.id}", data=cancelled, follow_redirects=False)
    db_session.refresh(mandate)
    assert updated.status_code == 303 and mandate.status == "cancelled"


def test_booking_links_only_active_compatible_mandate_and_supports_multiple_payers(client, db_session):
    owner, _, account, foreign, booking, person, second_person = _scenario(db_session)
    _create_profile(client, owner, account)
    profile = db_session.scalar(select(SepaCreditorProfile))
    mandate = SepaMandate(creditor_profile_id=profile.id, person_id=None, debtor_name="Tercero",
                          debtor_iban=GB_IBAN, mandate_reference="REF-A", signature_date=date(2026, 1, 1),
                          mandate_type="RCUR", status="draft")
    db_session.add(mandate); db_session.commit()
    inactive = client.post(f"/sepa/bookings/{booking.id}/link", data={"mandate_id": mandate.id}, follow_redirects=False)
    assert "sepa_mandate_not_active" in inactive.headers["location"]
    mandate.status = "active"; db_session.add(BookingParty(booking_id=booking.id, person_id=second_person.id, role="payer")); db_session.commit()
    linked = client.post(f"/sepa/bookings/{booking.id}/link", data={"mandate_id": mandate.id}, follow_redirects=False)
    assert "success=sepa_mandate_linked" in linked.headers["location"]
    page = client.get(f"/sepa/bookings/{booking.id}")
    assert page.status_code == 200
    assert "Hay varios responsables de pago" in page.text
    assert 'name="person_id"' in page.text

    foreign_profile = SepaCreditorProfile(display_name="Otro", creditor_name="Otro",
                                          creditor_identifier="ES12ZZZ87654321", owner_id=foreign.owner_id,
                                          bank_account_id=foreign.id, scheme="CORE", active=True)
    db_session.add(foreign_profile); db_session.flush()
    foreign_mandate = SepaMandate(creditor_profile_id=foreign_profile.id, debtor_name="Otro deudor",
                                  debtor_iban=GB_IBAN, mandate_reference="REF-B", signature_date=date(2026, 1, 1),
                                  mandate_type="RCUR", status="active")
    db_session.add(foreign_mandate); db_session.commit()
    rejected = client.post(f"/sepa/bookings/{booking.id}/link", data={"mandate_id": foreign_mandate.id}, follow_redirects=False)
    assert "sepa_mandate_property_incompatible" in rejected.headers["location"]


def test_sepa_data_is_admin_only_and_not_exposed_publicly(client, db_session):
    owner, _, account, _, booking, person, _ = _scenario(db_session)
    _create_profile(client, owner, account)
    profile = db_session.scalar(select(SepaCreditorProfile))
    mandate = SepaMandate(creditor_profile_id=profile.id, person_id=person.id,
                          debtor_name="Dato Privado", debtor_iban=ES_IBAN,
                          mandate_reference="SECRETO-SEPA", signature_date=date(2026, 1, 1),
                          mandate_type="RCUR", status="active")
    db_session.add(mandate); db_session.commit()
    for path in ("/", "/robots.txt", "/sitemap.xml"):
        response = client.get(path)
        assert ES_IBAN not in response.text
        assert "SECRETO-SEPA" not in response.text
        assert "Dato Privado" not in response.text
