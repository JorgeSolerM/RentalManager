from sqlalchemy import select

from backend.models.property import Property
from backend.models.rental_requirement import RentalRequirement


def test_create_property_uses_overridden_temporary_database(client, db_session):
    response = client.post(
        "/properties/create",
        data={
            "name": "Piso Universidad",
            "alias": "Universidad",
            "street": "Calle Universidad",
            "street_number": "1",
            "floor": "3",
            "door": "A",
            "city": "Elche",
            "owner": "HSI Rents",
            "notes": "Propiedad de prueba",
        },
        follow_redirects=False,
    )

    persisted_property = db_session.scalar(
        select(Property).where(Property.name == "Piso Universidad")
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/properties/?success=property_updated"
    assert persisted_property is not None
    assert persisted_property.address == "Calle Universidad 1, 3 A"
    assert persisted_property.street == "Calle Universidad"


def test_get_property_uses_overridden_temporary_database(client, db_session):
    property_obj = Property(
        name="Piso Centro",
        address="Calle Centro 2",
        city="Elche",
        owner="HSI Rents",
        active=True,
    )
    db_session.add(property_obj)
    db_session.commit()

    response = client.get(f"/properties/{property_obj.id}")

    assert response.status_code == 200
    assert response.json()["id"] == property_obj.id
    assert response.json()["name"] == "Piso Centro"
    assert response.json()["street"] is None
    assert response.json()["street_number"] is None
    assert response.json()["floor"] is None
    assert response.json()["door"] is None

    page = client.get("/properties/")
    assert page.status_code == 200
    assert 'id="property-legacy-address"' in page.text


def test_update_property_uses_structured_address(client, db_session):
    property_obj = Property(
        name="Piso Centro", address="Legacy", street="Calle Centro",
        street_number="2", city="Elche", owner="HSI Rents", active=True,
    )
    db_session.add(property_obj)
    db_session.commit()

    response = client.post(
        f"/properties/update/{property_obj.id}",
        data={
            "name": "Piso Centro", "alias": "", "street": "Calle Nueva",
            "street_number": "12B", "floor": "entlo", "door": "",
            "city": "Elche", "owner": "HSI Rents", "notes": "",
        },
        follow_redirects=False,
    )
    db_session.refresh(property_obj)
    assert response.status_code == 303
    assert property_obj.address == "Calle Nueva 12B, entlo"


def test_property_rules_page_and_save_use_tristate_and_requirements(
    client, db_session
):
    property_obj = Property(
        name="Piso Centro",
        address="Calle Centro 2",
        city="Elche",
        owner="HSI Rents",
        active=True,
    )
    requirement = RentalRequirement(
        slug="identity-document",
        public_name="Documento de identidad",
        active=True,
        display_order=10,
    )
    db_session.add_all([property_obj, requirement])
    db_session.commit()

    page = client.get(f"/properties/{property_obj.id}/publication/rules")
    response = client.post(
        f"/properties/{property_obj.id}/publication/rules",
        data={
            "smoking_allowed": "no",
            "pets_allowed": "yes",
            "musical_instruments_allowed": "unknown",
            "minimum_tenant_age": "18",
            "maximum_tenant_age": "48",
            "requirement_ids": str(requirement.id),
        },
        follow_redirects=False,
    )
    db_session.refresh(property_obj)

    assert page.status_code == 200
    assert "Normas y requisitos" in page.text
    assert "No informado" in page.text
    assert response.status_code == 303
    assert response.headers["location"].endswith("success=property_rules_saved")
    assert property_obj.smoking_allowed is False
    assert property_obj.pets_allowed is True
    assert {item.id for item in property_obj.requirements} == {requirement.id}
