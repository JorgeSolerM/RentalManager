from sqlalchemy import select

from backend.models.property import Property
from backend.services.property_service import PropertyService


def test_create_property_in_temporary_database(db_session):
    property_obj = Property(
        name="Piso Universidad",
        alias="Universidad",
        address="Calle Universidad 1",
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
