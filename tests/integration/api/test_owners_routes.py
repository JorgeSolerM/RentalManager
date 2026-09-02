from datetime import date
from decimal import Decimal

from sqlalchemy import select

from backend.models.owner import Owner
from backend.models.owner_bank_account import OwnerBankAccount
from backend.models.property import Property
from backend.models.property_ownership import PropertyOwnership


def make_property(db_session, name="Finca Centro"):
    item = Property(name=name, address="Calle 1", street="Calle", street_number="1", city="Elche", owner="", active=True)
    db_session.add(item)
    db_session.commit()
    return item


def test_owner_accounts_and_coproperty_flow(client, db_session):
    property_obj = make_property(db_session)
    response = client.post("/owners/create", data={"legal_name": "Titular Uno", "active": "true"}, follow_redirects=False)
    owner = db_session.scalar(select(Owner))
    assert response.status_code == 303
    assert owner.tax_id is None

    account_response = client.post(
        f"/owners/{owner.id}/accounts",
        data={"account_holder_name": "Titular Uno", "iban": "es91 2100 0418 4502 0005 1332", "active": "true", "receives_rent": "true", "receives_settlements": "true"},
        follow_redirects=False,
    )
    account = db_session.scalar(select(OwnerBankAccount))
    assert account_response.status_code == 303
    assert account.iban == "ES9121000418450200051332"
    assert account.receives_rent and account.receives_settlements
    second_response = client.post(
        f"/owners/{owner.id}/accounts",
        data={"account_holder_name": "Titular Uno", "iban": "GB82 WEST 1234 5698 7654 32", "active": "true", "receives_settlements": "true"},
        follow_redirects=False,
    )
    assert second_response.status_code == 303
    assert len(db_session.scalars(select(OwnerBankAccount)).all()) == 2

    linked = client.post(
        f"/owners/{owner.id}/ownerships",
        data={"property_id": property_obj.id, "ownership_percentage": "37.50", "rent_bank_account_id": account.id},
        follow_redirects=False,
    )
    ownership = db_session.scalar(select(PropertyOwnership))
    assert linked.status_code == 303
    assert ownership.ownership_percentage == Decimal("37.50")
    detail = client.get(f"/owners/{owner.id}")
    assert "Total activo: 37.50 %" in detail.text
    assert "ES9121000418450200051332" not in client.get("/owners").text

    disabled = client.post(
        f"/owners/{owner.id}/accounts/{account.id}",
        data={"account_holder_name": "Titular Uno", "iban": account.iban},
        follow_redirects=False,
    )
    assert "error=owner_account_in_use" in disabled.headers["location"]

    removed = client.post(f"/owners/{owner.id}/ownerships/{ownership.id}/deactivate", follow_redirects=False)
    db_session.refresh(ownership)
    assert removed.status_code == 303 and not ownership.active
    assert ownership.effective_until == date.today()
    assert db_session.get(PropertyOwnership, ownership.id) is ownership


def test_owner_ui_links_full_and_coownership_without_exposing_validity_fields(client, db_session):
    property_obj = make_property(db_session)
    first = Owner(legal_name="Copropietario A", active=True)
    second = Owner(legal_name="Copropietario B", active=True)
    db_session.add_all([first, second]); db_session.commit()
    for owner in (first, second):
        response = client.post(
            f"/owners/{owner.id}/ownerships",
            data={"property_id": property_obj.id, "ownership_percentage": "50"},
            follow_redirects=False,
        )
        assert response.status_code == 303
    ownerships = db_session.scalars(select(PropertyOwnership).where(PropertyOwnership.property_id == property_obj.id)).all()
    assert len(ownerships) == 2
    assert sum((item.ownership_percentage for item in ownerships), Decimal("0")) == Decimal("100.00")
    page = client.get(f"/owners/{first.id}")
    assert "Finca" in page.text and ">Property<" not in page.text
    assert 'name="effective_from"' not in page.text
    assert 'name="effective_until"' not in page.text


def test_owner_rejects_invalid_or_foreign_account_and_protects_delete(client, db_session):
    property_obj = make_property(db_session)
    first = Owner(legal_name="Primero", active=True)
    second = Owner(legal_name="Segundo", active=True)
    db_session.add_all([first, second]); db_session.commit()
    invalid = client.post(f"/owners/{first.id}/accounts", data={"account_holder_name": "X", "iban": "ES001"}, follow_redirects=False)
    assert "owner_account_iban_invalid" in invalid.headers["location"]
    account = OwnerBankAccount(owner_id=second.id, account_holder_name="Segundo", iban="ES9121000418450200051332", active=True, receives_rent=True)
    inactive = OwnerBankAccount(owner_id=first.id, account_holder_name="Primero", iban="GB82WEST12345698765432", active=False, receives_rent=True)
    db_session.add_all([account, inactive]); db_session.commit()
    foreign = client.post(f"/owners/{first.id}/ownerships", data={"property_id": property_obj.id, "ownership_percentage": "50", "rent_bank_account_id": account.id}, follow_redirects=False)
    assert "ownership_account_wrong_owner" in foreign.headers["location"]
    ineligible = client.post(f"/owners/{first.id}/ownerships", data={"property_id": property_obj.id, "ownership_percentage": "50", "rent_bank_account_id": inactive.id}, follow_redirects=False)
    assert "ownership_account_not_eligible" in ineligible.headers["location"]
    blocked = client.post(f"/owners/{second.id}/delete", follow_redirects=False)
    assert "owner_has_relations" in blocked.headers["location"]


def test_property_forms_use_ownership_not_legacy_owner(client, db_session):
    response = client.post("/properties/create", data={"name": "Nueva", "street": "Solars", "city": "Elche"}, follow_redirects=False)
    item = db_session.scalar(select(Property).where(Property.name == "Nueva"))
    assert response.status_code == 303 and item.owner == ""
    page = client.get("/properties/")
    assert "Sin propietario configurado" in page.text
    assert 'name="owner"' not in page.text
