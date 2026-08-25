from sqlalchemy import select

from backend.models.property import Property
from backend.services.property_service import PropertyService


def test_create_property_in_temporary_database(db_session):
    property_obj = Property(
        name="Piso Universidad",
        alias="Universidad",
        address="legacy",
        street="Calle Universidad",
        street_number="1",
        floor=" 3 ",
        door=" A ",
        city="Elche",
        owner="HSI Rents",
        notes="Propiedad de prueba",
        active=True,
    )

    result = PropertyService().create_property(db_session, property_obj)

    persisted_property = db_session.scalar(
        select(Property).where(Property.id == property_obj.id)
    )

    assert result.success is True
    assert property_obj.id is not None
    assert persisted_property is not None
    assert persisted_property.name == "Piso Universidad"
    assert persisted_property.address == "Calle Universidad 1, 3 A"


def test_property_service_validates_structured_address(db_session):
    result = PropertyService().create_property(db_session, Property(
        name="Sin calle", address="legacy", street=" ", city="Elche",
        owner="HSI Rents", active=True,
    ))
    assert not result.success
    assert result.message == "property_street_required"
