from datetime import date

from backend.models.booking import Booking
from backend.models.feature import Feature
from backend.models.media_asset import MediaAsset
from backend.models.manager import Manager
from backend.models.property import Property
from backend.models.property_photo import PropertyPhoto
from backend.models.room import Room
from backend.models.room_photo import RoomPhoto
from backend.services.publication_service import PublicationService


TODAY = date(2026, 8, 20)


def create_property_and_room(db_session):
    manager = Manager(name="Gestor", active=True)
    db_session.add(manager)
    db_session.flush()
    property_obj = Property(
        name="Internal name",
        address="Private address",
        city="Madrid",
        owner="Owner",
        active=True,
        manager_id=manager.id,
    )
    db_session.add(property_obj)
    db_session.flush()
    room = Room(
        property_id=property_obj.id,
        code="R1",
        display_order=1,
        base_price=650,
        active=True,
        minimum_stay_months=1,
    )
    db_session.add(room)
    bed = Feature(
        slug="cama-individual", name="Cama individual", scope="room",
        category="Dormitorio", display_order=0, active=True,
    )
    db_session.add(bed)
    room.features.append(bed)
    db_session.commit()
    return property_obj, room


def test_publication_requires_exactly_one_bed_capacity_feature(db_session):
    _, room = create_property_and_room(db_session)
    service = PublicationService()
    room.features.clear()
    db_session.commit()
    assert "room_bed_capacity_required" in service.assess_room(
        db_session, room.id
    ).reasons

    individual = db_session.query(Feature).filter_by(slug="cama-individual").one()
    double = Feature(
        slug="cama-doble", name="Cama doble", scope="room",
        category="Dormitorio", display_order=0, active=True,
    )
    room.features.extend([individual, double])
    db_session.add(double)
    db_session.commit()
    assert "room_bed_capacity_required" in service.assess_room(
        db_session, room.id
    ).reasons


def ready_asset(number: int) -> MediaAsset:
    return MediaAsset(
        storage_key=f"asset-{number}",
        mime_type="image/webp",
        width=1600,
        height=900,
        byte_size=1000,
        checksum_sha256=f"checksum-{number}",
        status="ready",
    )


def fill_public_fields(property_obj, room):
    property_obj.public_title = "Piso céntrico"
    property_obj.public_description = "Descripción común opcional"
    property_obj.public_location = "Centro, Madrid"
    property_obj.public_slug = "piso-centrico"
    property_obj.is_published = True
    room.public_title = "Habitación exterior"
    room.public_description = "Habitación amplia y luminosa."
    room.public_slug = "habitacion-exterior"
    room.is_published = True


def test_publication_assessment_reports_every_missing_requirement(db_session):
    property_obj, room = create_property_and_room(db_session)

    assessment = PublicationService().assess_room(db_session, room.id)

    assert assessment.is_publicable is False
    assert set(assessment.reasons) == {
        "property_not_published",
        "property_public_title_required",
        "property_public_location_required",
        "property_public_slug_required",
        "room_not_published",
        "room_public_title_required",
        "room_public_description_required",
        "room_public_slug_required",
        "public_photo_required",
    }
    assert "Private address" not in assessment.model_dump_json()
    assert property_obj.address == "Private address"


def test_price_must_be_strictly_positive_but_surface_is_optional(db_session):
    property_obj, room = create_property_and_room(db_session)
    fill_public_fields(property_obj, room)
    asset = ready_asset(1)
    db_session.add(asset); db_session.flush()
    db_session.add(RoomPhoto(room_id=room.id, media_asset_id=asset.id, position=0, is_primary=True))

    room.base_price = None
    room.square_meters = None
    db_session.commit()
    missing = PublicationService().assess_room(db_session, room.id)
    assert "room_price_invalid" in missing.reasons
    assert not any("square" in reason for reason in missing.reasons)

    room.base_price = 0
    db_session.commit()
    free = PublicationService().assess_room(db_session, room.id)
    assert "room_price_invalid" in free.reasons

    room.base_price = 1
    db_session.commit()
    valid = PublicationService().assess_room(db_session, room.id)
    assert valid.is_publicable


def test_room_can_publish_with_ready_property_photo_fallback(db_session):
    property_obj, room = create_property_and_room(db_session)
    fill_public_fields(property_obj, room)
    asset = ready_asset(1)
    db_session.add(asset)
    db_session.flush()
    db_session.add(PropertyPhoto(
        property_id=property_obj.id,
        media_asset_id=asset.id,
        position=0,
        is_primary=True,
    ))
    db_session.commit()

    assessment = PublicationService().assess_room(db_session, room.id)

    assert assessment.is_publicable is True
    assert assessment.reasons == []
    assert assessment.primary_photo_source == "property"


def test_ready_room_primary_photo_takes_precedence_and_processing_is_not_usable(
    db_session,
):
    property_obj, room = create_property_and_room(db_session)
    fill_public_fields(property_obj, room)
    processing = ready_asset(1)
    processing.status = "processing"
    room_asset = ready_asset(2)
    db_session.add_all([processing, room_asset])
    db_session.flush()
    db_session.add_all([
        PropertyPhoto(
            property_id=property_obj.id, media_asset_id=processing.id,
            position=0, is_primary=True,
        ),
        RoomPhoto(
            room_id=room.id, media_asset_id=room_asset.id,
            position=0, is_primary=True,
        ),
    ])
    db_session.commit()

    assessment = PublicationService().assess_room(db_session, room.id)

    assert assessment.is_publicable is True
    assert assessment.primary_photo_source == "room"


def test_inactive_property_or_room_blocks_publication(db_session):
    property_obj, room = create_property_and_room(db_session)
    fill_public_fields(property_obj, room)
    asset = ready_asset(1)
    db_session.add(asset); db_session.flush()
    db_session.add(RoomPhoto(
        room_id=room.id, media_asset_id=asset.id, position=0, is_primary=True
    ))
    property_obj.active = False
    room.active = False
    db_session.commit()

    assessment = PublicationService().assess_room(db_session, room.id)

    assert "property_inactive" in assessment.reasons
    assert "room_inactive" in assessment.reasons
    assert assessment.is_publicable is False


def test_feature_catalog_is_ordered_and_scope_assignment_is_explicit(db_session):
    features = [
        Feature(
            slug="desk", name="Escritorio", scope="room",
            category="mobiliario", display_order=2, active=True,
        ),
        Feature(
            slug="wifi", name="Wi-Fi", scope="both",
            category="conectividad", display_order=1, active=True,
        ),
        Feature(
            slug="lift", name="Ascensor", scope="property",
            category="edificio", display_order=1, active=False,
        ),
    ]
    db_session.add_all(features)
    db_session.commit()
    service = PublicationService()

    catalog = service.list_feature_catalog(db_session)

    assert [item.slug for item in catalog] == ["wifi", "desk"]
    assert service.feature_can_apply_to(features[0], "room") is True
    assert service.feature_can_apply_to(features[0], "property") is False
    assert service.feature_can_apply_to(features[1], "property") is True
    assert service.feature_can_apply_to(features[2], "room") is False


def test_public_availability_consolidates_contiguous_and_overlapping_intervals(
    db_session,
):
    _property_obj, room = create_property_and_room(db_session)
    db_session.add_all([
        Booking(
            room_id=room.id, origin="manual",
            check_in=date(2026, 8, 18), check_out=date(2026, 8, 22),
        ),
        Booking(
            room_id=room.id, origin="manual",
            check_in=date(2026, 8, 22), check_out=date(2026, 8, 25),
        ),
        Booking(
            room_id=room.id, origin="manual",
            check_in=date(2026, 8, 24), check_out=date(2026, 8, 28),
        ),
    ])
    db_session.commit()

    result = PublicationService().get_public_availability(
        db_session, room.id, today=TODAY
    )

    assert result.status == "available_from"
    assert result.available_from == date(2026, 8, 28)
    assert set(result.model_dump()) == {
        "status", "available_from", "available_until"
    }


def test_expected_dates_do_not_change_public_availability(db_session):
    _property_obj, room = create_property_and_room(db_session)
    db_session.add(Booking(
        room_id=room.id,
        origin="manual",
        check_in=date(2026, 8, 18),
        check_out=date(2026, 8, 28),
        expected_arrival_date=date(2026, 8, 21),
        expected_departure_date=date(2026, 8, 22),
    ))
    db_session.commit()

    result = PublicationService().get_public_availability(
        db_session, room.id, today=TODAY
    )

    assert result.status == "available_from"
    assert result.available_from == date(2026, 8, 28)


def test_public_availability_treats_checkout_today_and_future_booking_as_free_now(
    db_session,
):
    _property_obj, room = create_property_and_room(db_session)
    room.minimum_stay_months = 0
    db_session.add_all([
        Booking(
            room_id=room.id, origin="manual",
            check_in=date(2026, 8, 18), check_out=TODAY,
        ),
        Booking(
            room_id=room.id, origin="manual",
            check_in=date(2026, 9, 1), check_out=date(2026, 9, 10),
        ),
    ])
    db_session.commit()

    result = PublicationService().get_public_availability(
        db_session, room.id, today=TODAY
    )

    assert result.status == "available_period"
    assert result.available_from == TODAY
    assert result.available_until == date(2026, 8, 31)


def add_photo(db, owner, asset, position, primary=False):
    db.add(asset)
    db.flush()
    if isinstance(owner, Room):
        photo = RoomPhoto(
            room_id=owner.id, media_asset_id=asset.id,
            position=position, is_primary=primary,
        )
    else:
        photo = PropertyPhoto(
            property_id=owner.id, media_asset_id=asset.id,
            position=position, is_primary=primary,
        )
    db.add(photo)
    return photo


def test_effective_gallery_combines_room_then_property_with_independent_order(db_session):
    property_obj, room = create_property_and_room(db_session)
    room_first = ready_asset(10)
    room_second = ready_asset(11)
    property_first = ready_asset(12)
    property_second = ready_asset(13)
    add_photo(db_session, room, room_first, 0, True)
    add_photo(db_session, room, room_second, 1)
    add_photo(db_session, property_obj, property_first, 0, True)
    add_photo(db_session, property_obj, property_second, 1)
    db_session.commit()

    gallery = PublicationService().get_effective_gallery(db_session, room.id)

    assert [item.asset_id for item in gallery] == [
        room_first.id, room_second.id, property_first.id, property_second.id,
    ]
    assert [item.source for item in gallery] == ["room", "room", "property", "property"]
    assert all(not isinstance(item, (RoomPhoto, PropertyPhoto)) for item in gallery)


def test_effective_gallery_supports_each_empty_combination(db_session):
    property_obj, room = create_property_and_room(db_session)
    property_asset = ready_asset(20)
    add_photo(db_session, property_obj, property_asset, 0, True)
    db_session.commit()
    service = PublicationService()
    assert [item.source for item in service.get_effective_gallery(db_session, room.id)] == ["property"]

    db_session.query(PropertyPhoto).delete()
    room_asset = ready_asset(21)
    add_photo(db_session, room, room_asset, 0, True)
    db_session.commit()
    assert [item.source for item in service.get_effective_gallery(db_session, room.id)] == ["room"]

    db_session.query(RoomPhoto).delete()
    db_session.commit()
    assert service.get_effective_gallery(db_session, room.id) == ()


def test_effective_primary_prefers_room_then_falls_back_to_property(db_session):
    property_obj, room = create_property_and_room(db_session)
    property_asset = ready_asset(30)
    room_asset = ready_asset(31)
    property_photo = add_photo(db_session, property_obj, property_asset, 0, True)
    room_photo = add_photo(db_session, room, room_asset, 0, True)
    db_session.commit()
    service = PublicationService()

    primary = service.get_effective_primary_photo(db_session, room.id)
    assert (primary.asset_id, primary.source) == (room_asset.id, "room")
    db_session.delete(room_photo)
    db_session.commit()
    primary = service.get_effective_primary_photo(db_session, room.id)
    assert (primary.asset_id, primary.source) == (property_asset.id, "property")
    db_session.delete(property_photo)
    db_session.commit()
    assert service.get_effective_primary_photo(db_session, room.id) is None


def test_effective_gallery_deduplicates_shared_asset_in_favor_of_room(db_session):
    property_obj, room = create_property_and_room(db_session)
    shared = ready_asset(40)
    add_photo(db_session, room, shared, 0, True)
    db_session.flush()
    db_session.add(PropertyPhoto(
        property_id=property_obj.id, media_asset_id=shared.id,
        position=0, is_primary=True,
    ))
    db_session.commit()

    gallery = PublicationService().get_effective_gallery(db_session, room.id)
    assert len(gallery) == 1
    assert gallery[0].source == "room"
    assert db_session.query(RoomPhoto).count() == 1


def test_property_photo_changes_are_reflected_without_room_copy(db_session):
    property_obj, room = create_property_and_room(db_session)
    old_asset = ready_asset(50)
    old_photo = add_photo(db_session, property_obj, old_asset, 0, True)
    db_session.commit()
    service = PublicationService()
    assert [item.asset_id for item in service.get_effective_gallery(db_session, room.id)] == [old_asset.id]

    db_session.delete(old_photo)
    db_session.flush()
    new_asset = ready_asset(51)
    add_photo(db_session, property_obj, new_asset, 0, True)
    db_session.commit()

    assert [item.asset_id for item in service.get_effective_gallery(db_session, room.id)] == [new_asset.id]
    assert db_session.query(RoomPhoto).count() == 0
