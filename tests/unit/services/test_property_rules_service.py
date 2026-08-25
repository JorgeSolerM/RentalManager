import pytest
from sqlalchemy import select

from backend.models.property import Property
from backend.models.rental_requirement import RentalRequirement
from backend.services.property_rules_service import PropertyRulesService


def property_record() -> Property:
    return Property(
        name="Property",
        address="Calle 1",
        street="Calle",
        street_number="1",
        city="Elche",
        owner="Owner",
        active=True,
    )


def test_property_rules_save_tristate_ages_and_replace_requirements(db_session):
    property_obj = property_record()
    identity = RentalRequirement(
        slug="identity-document",
        public_name="Documento de identidad",
        active=True,
        display_order=10,
    )
    income = RentalRequirement(
        slug="income-proof",
        public_name="Justificante de ingresos",
        active=True,
        display_order=20,
    )
    db_session.add_all([property_obj, identity, income])
    db_session.commit()

    service = PropertyRulesService()
    result = service.update(
        db_session,
        property_obj.id,
        smoking_allowed="no",
        pets_allowed="yes",
        musical_instruments_allowed="unknown",
        minimum_tenant_age="18",
        maximum_tenant_age="48",
        requirement_ids=[identity.id, income.id],
    )
    assert result.success
    assert property_obj.smoking_allowed is False
    assert property_obj.pets_allowed is True
    assert (property_obj.minimum_tenant_age, property_obj.maximum_tenant_age) == (18, 48)
    assert {item.id for item in property_obj.requirements} == {identity.id, income.id}

    result = service.update(
        db_session,
        property_obj.id,
        smoking_allowed="unknown",
        pets_allowed="unknown",
        musical_instruments_allowed="unknown",
        minimum_tenant_age="",
        maximum_tenant_age="",
        requirement_ids=[income.id],
    )
    assert result.success
    assert property_obj.smoking_allowed is None
    assert property_obj.minimum_tenant_age is None
    assert [item.id for item in property_obj.requirements] == [income.id]


def test_property_rules_reject_invalid_age_range_and_new_inactive_requirement(db_session):
    property_obj = property_record()
    inactive = RentalRequirement(
        slug="inactive", public_name="Inactivo", active=False, display_order=0
    )
    db_session.add_all([property_obj, inactive])
    db_session.commit()
    service = PropertyRulesService()

    invalid_age = service.update(
        db_session,
        property_obj.id,
        smoking_allowed="unknown",
        pets_allowed="unknown",
        musical_instruments_allowed="unknown",
        minimum_tenant_age="49",
        maximum_tenant_age="48",
        requirement_ids=[],
    )
    inactive_result = service.update(
        db_session,
        property_obj.id,
        smoking_allowed="unknown",
        pets_allowed="unknown",
        musical_instruments_allowed="unknown",
        minimum_tenant_age="",
        maximum_tenant_age="",
        requirement_ids=[inactive.id],
    )
    assert (invalid_age.success, invalid_age.message) == (False, "property_age_range_invalid")
    assert (inactive_result.success, inactive_result.message) == (False, "requirement_inactive")
    assert property_obj.requirements == []


def test_property_rules_roll_back_all_fields_and_requirements(db_session, monkeypatch):
    property_obj = property_record()
    requirement = RentalRequirement(
        slug="identity", public_name="Identidad", active=True, display_order=0
    )
    db_session.add_all([property_obj, requirement])
    db_session.commit()
    original_commit = db_session.commit

    def fail_commit():
        raise RuntimeError("commit failed")

    monkeypatch.setattr(db_session, "commit", fail_commit)
    with pytest.raises(RuntimeError):
        PropertyRulesService().update(
            db_session,
            property_obj.id,
            smoking_allowed="yes",
            pets_allowed="no",
            musical_instruments_allowed="unknown",
            minimum_tenant_age="18",
            maximum_tenant_age="",
            requirement_ids=[requirement.id],
        )
    monkeypatch.setattr(db_session, "commit", original_commit)
    db_session.expire_all()
    stored = db_session.scalar(select(Property).where(Property.id == property_obj.id))
    assert stored.smoking_allowed is None
    assert stored.minimum_tenant_age is None
    assert stored.requirements == []
