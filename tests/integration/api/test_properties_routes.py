from sqlalchemy import select

from backend.models.property import Property


def test_create_property_uses_overridden_temporary_database(client, db_session):
    response = client.post(
        "/properties/create",
        data={
            "name": "Piso Universidad",
            "alias": "Universidad",
            "address": "Calle Universidad 1",
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
