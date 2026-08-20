from backend.models.feature import Feature
from backend.models.media_asset import MediaAsset
from backend.models.property import Property
from backend.models.property_photo import PropertyPhoto
from backend.models.room import Room
from backend.models.room_photo import RoomPhoto
from backend.services.commercial_publication_service import CommercialPublicationService


def records(db):
    prop = Property(name="Internal", address="Private", city="Elche", owner="Owner", active=True)
    db.add(prop); db.flush()
    room = Room(property_id=prop.id, code="R1", display_order=1, base_price=600, square_meters=12, active=True)
    db.add(room); db.commit(); return prop, room


def asset(db, number=1):
    item = MediaAsset(storage_key=f"{number:032x}", mime_type="image/webp", width=800, height=600, byte_size=100, checksum_sha256=f"{number:064x}", status="ready")
    db.add(item); db.flush(); return item


def test_saves_property_public_fields_and_features_without_internal_backfill(db_session):
    prop, _ = records(db_session)
    feature = Feature(slug="ascensor", name="Ascensor", scope="property", category="Edificio", display_order=1, active=True)
    db_session.add(feature); db_session.commit()
    result = CommercialPublicationService().update_property(
        db_session, prop.id, title="Piso universitario",
        location="Zona UMH · Elche", slug="piso-universitario", is_published=True,
        feature_ids=[feature.id],
    )
    db_session.refresh(prop)
    assert result.success
    assert (prop.public_title, prop.public_location, prop.public_slug, prop.is_published) == ("Piso universitario", "Zona UMH · Elche", "piso-universitario", True)
    assert [f.id for f in prop.features] == [feature.id]
    assert prop.address == "Private" and prop.name == "Internal"


def test_invalid_room_publish_keeps_draft_but_not_publish_flag(db_session):
    prop, room = records(db_session)
    result = CommercialPublicationService().update_room(
        db_session, room.id, title="Habitación luminosa", description="Amplia",
        base_price="600", square_meters="12", is_published=True, feature_ids=[],
    )
    db_session.refresh(room)
    assert not result.success and result.message == "publication_requirements"
    assert room.public_title == "Habitación luminosa"
    assert room.is_published is False
    assert "property_not_published" in result.data and "public_photo_required" in result.data


def test_valid_room_can_publish_with_property_gate_and_effective_photo(db_session):
    prop, room = records(db_session)
    prop.public_title = "Piso"; prop.public_location = "Centro"; prop.public_slug = "piso"; prop.is_published = True
    photo_asset = asset(db_session)
    db_session.add(PropertyPhoto(property_id=prop.id, media_asset_id=photo_asset.id, position=0, is_primary=True)); db_session.commit()
    result = CommercialPublicationService().update_room(db_session, room.id, title="Habitación", description="Descripción", base_price="600", square_meters="12", is_published=True, feature_ids=[])
    assert result.success and result.data.is_published


def test_room_slug_is_automatic_unique_and_stable(db_session):
    prop, room = records(db_session)
    prop.public_slug = "solars-10"
    room.code = "Solars08"
    other = Room(property_id=prop.id, code="Other08", display_order=2, base_price=500, active=True, public_slug="solars-10-h08")
    db_session.add(other); db_session.commit()
    service = CommercialPublicationService()
    assert service.update_room(db_session, room.id, title="Título A", description="D", base_price="600", square_meters="12", is_published=False, feature_ids=[]).success
    generated = room.public_slug
    assert generated == f"solars-10-h08-{room.id}"
    prop.public_slug = "otro-inmueble"
    assert service.update_room(db_session, room.id, title="Título B", description="D", base_price="650", square_meters="13", is_published=False, feature_ids=[]).success
    assert room.public_slug == generated


def test_room_without_property_slug_keeps_public_slug_empty(db_session):
    _, room = records(db_session)
    result = CommercialPublicationService().update_room(db_session, room.id, title="T", description="D", base_price="600", square_meters="", is_published=False, feature_ids=[])
    assert result.success
    assert room.public_slug is None


def test_feature_scope_and_inactive_legacy_assignment(db_session):
    prop, room = records(db_session)
    legacy = Feature(slug="legado", name="Legado", scope="room", category="Room", display_order=1, active=False)
    wrong = Feature(slug="solo-property", name="Property", scope="property", category="P", display_order=1, active=True)
    inactive_new = Feature(slug="inactiva", name="Inactiva", scope="room", category="R", display_order=2, active=False)
    db_session.add_all([legacy, wrong, inactive_new]); db_session.flush(); room.features.append(legacy); db_session.commit()
    service = CommercialPublicationService()
    assert service.update_room(db_session, room.id, title="T", description="D", base_price="600", square_meters="12", is_published=False, feature_ids=[]).success
    assert [f.id for f in room.features] == [legacy.id]
    assert service.update_room(db_session, room.id, title="T", description="D", base_price="600", square_meters="12", is_published=False, feature_ids=[wrong.id]).message == "feature_wrong_scope"
    assert service.update_room(db_session, room.id, title="T", description="D", base_price="600", square_meters="12", is_published=False, feature_ids=[inactive_new.id]).message == "feature_inactive"


def test_technical_failure_rolls_back(db_session, monkeypatch):
    prop, _ = records(db_session)
    original = db_session.commit
    monkeypatch.setattr(db_session, "commit", lambda: (_ for _ in ()).throw(RuntimeError("fail")))
    try:
        try: CommercialPublicationService().update_property(db_session, prop.id, title="Changed", location="Centro", slug="changed", is_published=False, feature_ids=[])
        except RuntimeError: pass
    finally: monkeypatch.setattr(db_session, "commit", original)
    db_session.refresh(prop)
    assert prop.public_title is None


def test_room_commercial_save_rolls_back_all_fields_on_commit_error(db_session, monkeypatch):
    prop, room = records(db_session)
    prop.public_slug = "property"
    db_session.commit()
    original = db_session.commit
    monkeypatch.setattr(db_session, "commit", lambda: (_ for _ in ()).throw(RuntimeError("fail")))
    try:
        try:
            CommercialPublicationService().update_room(
                db_session, room.id, title="Changed", description="Changed",
                base_price="999", square_meters="20", is_published=False,
                feature_ids=[],
            )
        except RuntimeError:
            pass
    finally:
        monkeypatch.setattr(db_session, "commit", original)
    db_session.refresh(room)
    assert room.public_title is None
    assert float(room.base_price) == 600
    assert float(room.square_meters) == 12
    assert room.public_slug is None


def test_feature_options_query_count_is_constant(db_session):
    from sqlalchemy import event
    prop, _ = records(db_session)
    db_session.add_all([Feature(slug=f"f-{i}", name=f"F {i}", scope="property", category="C", display_order=i, active=True) for i in range(20)])
    db_session.commit(); prop_id = prop.id
    db_session.expire_all(); prop = db_session.get(Property, prop_id)
    count = 0
    def increment(*_):
        nonlocal count; count += 1
    event.listen(db_session.bind, "before_cursor_execute", increment)
    try: options = CommercialPublicationService().feature_options(db_session, prop)
    finally: event.remove(db_session.bind, "before_cursor_execute", increment)
    assert len(options) == 20
    assert count <= 2
