import pytest

from backend.models.feature import Feature
from backend.models.media_asset import MediaAsset
from backend.models.manager import Manager
from backend.models.property import Property
from backend.models.property_photo import PropertyPhoto
from backend.models.room import Room
from backend.models.room_public_highlight import RoomPublicHighlight
from backend.services.commercial_publication_service import CommercialPublicationService


def records(db):
    manager = Manager(name="Gestor", active=True)
    db.add(manager); db.flush()
    prop = Property(name="Internal P", address="Secret address", city="Elche", owner="Private owner", active=True, manager_id=manager.id)
    db.add(prop); db.flush()
    room = Room(property_id=prop.id, code="R1", display_order=1, base_price=650, square_meters=11, active=True)
    db.add(room); db.commit(); return prop, room


def test_property_publication_page_and_save_do_not_render_private_fields(client, db_session):
    prop, _ = records(db_session)
    prop.public_description = "Valor legado que no se edita"
    db_session.commit()
    page = client.get(f"/properties/{prop.id}/publication")
    assert page.status_code == 200
    assert "Título público" in page.text and "Estado de publicabilidad" in page.text
    assert 'name="public_description"' not in page.text
    assert "Valor legado que no se edita" not in page.text
    assert "Secret address" not in page.text and "Private owner" not in page.text
    assert 'name="shared_full_bathroom_count"' in page.text
    assert 'name="shared_toilet_count"' in page.text
    response = client.post(f"/properties/{prop.id}/publication", data={
        "public_title": "Piso", "public_location": "Zona UMH",
        "public_slug": "piso", "is_published": "on", "manager_id": str(prop.manager_id),
        "shared_full_bathroom_count": "1", "shared_toilet_count": "2",
    }, follow_redirects=False)
    assert response.status_code == 303 and "success=publication_saved" in response.headers["location"]
    db_session.refresh(prop)
    assert prop.is_published and prop.public_location == "Zona UMH"
    assert prop.shared_full_bathroom_count == 1
    assert prop.shared_toilet_count == 2
    assert prop.public_description == "Valor legado que no se edita"

    invalid = client.post(f"/properties/{prop.id}/publication", data={
        "public_title": "Piso", "public_location": "Zona UMH",
        "public_slug": "piso", "manager_id": str(prop.manager_id),
        "shared_full_bathroom_count": "-1",
    }, follow_redirects=False)
    assert "error=property_shared_bathroom_counts_invalid" in invalid.headers["location"]


def test_room_invalid_publish_keeps_draft_and_redirects_to_publication(client, db_session):
    _, room = records(db_session)
    response = client.post(f"/rooms/{room.id}/publication", data={
        "public_title": "Habitación", "public_description": "Descripción",
        "base_price": "650", "square_meters": "11", "is_published": "on",
    }, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith(f"/rooms/{room.id}/publication?")
    assert "error=publication_requirements" in response.headers["location"]
    db_session.refresh(room)
    assert room.public_title == "Habitación" and not room.is_published


def test_room_publication_shows_own_features_and_inherited_property_data(client, db_session):
    prop, room = records(db_session)
    prop.public_title = "Piso compartido"
    prop.public_location = "Zona UMH · Elche"
    room_feature = Feature(slug="desk", name="Escritorio", scope="room", category="Dormitorio", display_order=1, active=True)
    property_feature = Feature(slug="lift", name="Ascensor", scope="property", category="Edificio", display_order=1, active=True)
    legacy = Feature(slug="legacy", name="Legado", scope="room", category="Dormitorio", display_order=2, active=False)
    asset = MediaAsset(storage_key="1" * 32, mime_type="image/webp", width=800, height=600, byte_size=100, checksum_sha256="1" * 64, status="ready")
    db_session.add_all([room_feature, property_feature, legacy, asset]); db_session.flush()
    room.features.append(legacy)
    prop.features.append(property_feature)
    db_session.add(PropertyPhoto(property_id=prop.id, media_asset_id=asset.id, position=0, is_primary=True))
    db_session.commit()

    page = client.get(f"/rooms/{room.id}/publication")
    assert page.status_code == 200
    assert "Escritorio" in page.text and "Legado" in page.text and "(inactiva)" in page.text
    assert "Ascensor" in page.text
    assert "Zona UMH · Elche" in page.text
    assert "Fotografías comunes</dt><dd>1" in page.text
    assert f'href="/properties/{prop.id}/publication"' in page.text
    assert 'name="public_location"' not in page.text
    assert "Guardar publicación" in page.text


def test_room_list_is_primary_publication_entry_and_workspace_has_only_secondary_link(client, db_session):
    prop, room = records(db_session)
    listing = client.get(f"/rooms/property/{prop.id}")
    workspace = client.get(f"/rooms/{room.id}?tab=configuracion")

    assert listing.status_code == 200
    assert f'href="/rooms/{room.id}/publication"' in listing.text
    assert "Publicación" in listing.text
    assert workspace.status_code == 200
    assert f'href="/rooms/{room.id}/publication"' in workspace.text
    assert "Abrir publicación" in workspace.text
    assert 'name="public_title"' not in workspace.text
    assert 'data-photo-gallery' not in workspace.text

    publication = client.get(f"/rooms/{room.id}/publication")
    assert publication.status_code == 200
    assert 'data-photo-upload-form' in publication.text
    assert f'value="/rooms/{room.id}/publication"' in publication.text


def test_inherited_property_changes_are_visible_without_room_copies(client, db_session):
    prop, room = records(db_session)
    feature = Feature(slug="wifi", name="Wi-Fi", scope="property", category="Comunes", display_order=1, active=True)
    db_session.add(feature); db_session.flush()
    prop.public_location = "Centro · Elche"
    prop.features.append(feature)
    db_session.commit()

    first = client.get(f"/rooms/{room.id}/publication")
    assert "Centro · Elche" in first.text and "Wi-Fi" in first.text
    assert feature not in room.features

    prop.public_location = "Zona UMH · Elche"
    prop.features.remove(feature)
    db_session.commit()
    second = client.get(f"/rooms/{room.id}/publication")
    assert "Zona UMH · Elche" in second.text
    assert "Características comunes</dt><dd>Ninguna" in second.text
    assert feature not in room.features


def test_room_features_are_independent_even_when_sibling_rooms_share_a_property(client, db_session):
    prop, first_room = records(db_session)
    second_room = Room(property_id=prop.id, code="R2", display_order=2, base_price=675, square_meters=12, active=True)
    desk = Feature(slug="desk", name="Escritorio", scope="room", category="Mobiliario", display_order=1, active=True)
    wifi = Feature(slug="wifi", name="Wi-Fi", scope="property", category="Comunes", display_order=1, active=True)
    db_session.add_all([second_room, desk, wifi]); db_session.flush()
    first_room.features.append(desk)
    prop.features.append(wifi)
    db_session.commit()

    first_page = client.get(f"/rooms/{first_room.id}/publication")
    second_page = client.get(f"/rooms/{second_room.id}/publication")

    assert desk in first_room.features
    assert desk not in second_room.features
    assert "Wi-Fi" in first_page.text and "Wi-Fi" in second_page.text
    assert 'value="{}"\n                checked'.format(desk.id) in first_page.text
    assert 'value="{}"\n                checked'.format(desk.id) not in second_page.text

def test_missing_inherited_public_location_blocks_room_without_room_location_input(client, db_session):
    prop, room = records(db_session)
    prop.public_title = "Inmueble"
    prop.public_description = "Descripción"
    prop.public_slug = "inmueble"
    prop.is_published = True
    room.public_title = "Habitación"
    room.public_description = "Descripción"
    room.public_slug = "habitacion"
    db_session.commit()

    page = client.get(f"/rooms/{room.id}/publication")
    assert "Falta la ubicación pública del inmueble." in page.text
    assert 'name="public_location"' not in page.text


def test_room_publication_saves_commercial_values_and_automatic_slug(client, db_session):
    prop, room = records(db_session)
    prop.public_slug = "solars-10"
    room.code = "Solars08"
    room.base_price = None
    room.square_meters = None
    db_session.commit()

    page = client.get(f"/rooms/{room.id}/publication")
    assert 'name="base_price"' in page.text
    assert 'name="square_meters"' in page.text
    assert "/habitaciones/solars-10-h08" in page.text
    assert 'name="public_slug"' not in page.text
    assert "Falta un slug válido" not in page.text
    assert "Configura primero el slug público del inmueble." not in page.text

    response = client.post(f"/rooms/{room.id}/publication", data={
        "public_title": "Habitación exterior",
        "public_description": "Descripción",
        "base_price": "725.50",
        "square_meters": "13.25",
    }, follow_redirects=False)
    assert response.status_code == 303
    assert "success=publication_saved" in response.headers["location"]
    db_session.refresh(room)
    assert float(room.base_price) == 725.5
    assert float(room.square_meters) == 13.25
    assert room.public_slug == "solars-10-h08"

    prop.public_slug = "changed-property"
    db_session.commit()
    client.post(f"/rooms/{room.id}/publication", data={
        "public_title": "Título cambiado",
        "public_description": "Descripción",
        "base_price": "725.50",
        "square_meters": "",
    })
    db_session.refresh(room)
    assert room.public_slug == "solars-10-h08"
    assert room.square_meters is None


def test_room_without_property_slug_explains_that_property_must_be_configured(client, db_session):
    prop, room = records(db_session)
    page = client.get(f"/rooms/{room.id}/publication")
    assert "Configura primero el slug público del inmueble." in page.text
    assert f'href="/properties/{prop.id}/publication"' in page.text


def test_settings_feature_catalog_crud_contract(client, db_session):
    response = client.post("/settings/features/create", data={
        "name": "Escritorio", "slug": "escritorio", "scope": "room",
        "category": "Dormitorio", "display_order": "10", "active": "on",
    }, follow_redirects=False)
    assert response.status_code == 303 and "success=feature_saved" in response.headers["location"]
    page = client.get("/settings/features")
    assert "Características" in page.text and "escritorio" in page.text


def test_room_highlights_accept_only_effective_features_and_keep_order(client, db_session):
    prop, room = records(db_session)
    own = Feature(slug="private-bath", name="Baño privado", scope="room", category="Privado", display_order=1, active=True)
    common = Feature(slug="utilities", name="Suministros incluidos", scope="property", category="Condiciones", display_order=2, active=True)
    unrelated = Feature(slug="other", name="Otra", scope="room", category="Otros", display_order=3, active=True)
    db_session.add_all([own, common, unrelated]); db_session.flush()
    room.features.append(own); prop.features.append(common); db_session.commit()
    page = client.get(f"/rooms/{room.id}/publication")
    assert "De la habitación" in page.text and "De la habitación</div>" in page.text
    assert "Del inmueble" in page.text and "Suministros incluidos" in page.text
    response = client.post(f"/rooms/{room.id}/publication", data={
        "public_title": "Habitación", "public_description": "Descripción", "base_price": "650",
        "feature_ids": [str(own.id)], "highlight_feature_ids": [str(common.id), str(own.id)],
    }, follow_redirects=False)
    assert "success=publication_saved" in response.headers["location"]
    highlights = list(db_session.query(RoomPublicHighlight).order_by(RoomPublicHighlight.position))
    assert [(item.feature_id, item.position) for item in highlights] == [(common.id, 0), (own.id, 1)]
    rejected = client.post(f"/rooms/{room.id}/publication", data={
        "public_title": "Habitación", "public_description": "Descripción", "base_price": "650",
        "feature_ids": [str(own.id)], "highlight_feature_ids": [str(unrelated.id)],
    }, follow_redirects=False)
    assert "error=highlight_invalid" in rejected.headers["location"]

    # Removing an inherited feature also removes only the highlight that is no
    # longer effective; the room-owned highlight remains and keeps its order.
    client.post(f"/properties/{prop.id}/publication", data={
        "public_title": "Inmueble", "public_location": "Zona",
        "public_slug": "inmueble", "manager_id": str(prop.manager_id),
    }, follow_redirects=False)
    db_session.expire_all()
    highlights = list(db_session.query(RoomPublicHighlight).order_by(RoomPublicHighlight.position))
    assert [(item.feature_id, item.position) for item in highlights] == [(own.id, 0)]

    # Removing the room feature cleans its highlight in the same transaction.
    client.post(f"/rooms/{room.id}/publication", data={
        "public_title": "Habitación", "public_description": "Descripción", "base_price": "650",
        "highlight_feature_ids": [str(own.id)],
    }, follow_redirects=False)
    assert db_session.query(RoomPublicHighlight).count() == 0


def test_room_highlights_can_insert_and_reorder_without_transient_position_conflicts(
    client, db_session
):
    prop, room = records(db_session)
    own_first = Feature(
        slug="first-own", name="Primera", scope="room", category="Privado",
        display_order=1, active=True,
    )
    own_last = Feature(
        slug="last-own", name="Última", scope="room", category="Privado",
        display_order=2, active=True,
    )
    street_view = Feature(
        slug="street-view", name="Vistas a la calle", scope="room",
        category="Privado", display_order=3, active=True,
    )
    inherited = Feature(
        slug="inherited", name="Heredada", scope="property",
        category="Común", display_order=1, active=True,
    )
    db_session.add_all([own_first, own_last, street_view, inherited])
    db_session.flush()
    room.features.extend([own_first, own_last, street_view])
    prop.features.append(inherited)
    room.public_highlights.extend([
        RoomPublicHighlight(feature_id=own_first.id, position=0),
        RoomPublicHighlight(feature_id=inherited.id, position=1),
        RoomPublicHighlight(feature_id=own_last.id, position=2),
    ])
    db_session.commit()

    response = client.post(
        f"/rooms/{room.id}/publication",
        data={
            "public_title": "Habitación",
            "public_description": "Descripción",
            "base_price": "650",
            "feature_ids": [
                str(own_first.id), str(own_last.id), str(street_view.id)
            ],
            "highlight_feature_ids": [
                str(own_first.id), str(street_view.id), str(inherited.id),
                str(own_last.id), str(street_view.id),
            ],
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "success=publication_saved" in response.headers["location"]
    db_session.expire_all()
    highlights = list(
        db_session.query(RoomPublicHighlight)
        .filter(RoomPublicHighlight.room_id == room.id)
        .order_by(RoomPublicHighlight.position)
    )
    assert [(item.feature_id, item.position) for item in highlights] == [
        (own_first.id, 0),
        (street_view.id, 1),
        (inherited.id, 2),
        (own_last.id, 3),
    ]


def test_manager_is_assigned_to_property_and_inherited_by_room(client, db_session):
    prop, room = records(db_session)
    page = client.get(f"/rooms/{room.id}/publication")
    assert "Gestor heredado</dt><dd>Gestor" in page.text
    assert 'name="manager_id"' not in page.text
    managers_page = client.get("/settings/managers")
    assert managers_page.status_code == 200 and "Gestor" in managers_page.text


def test_copy_room_configuration_replaces_features_copies_text_and_keeps_valid_highlights(client, db_session):
    target_property, target = records(db_session)
    source_property = Property(name="Other", address="A", city="C", owner="O", active=True)
    source = Room(property=source_property, code="Template", display_order=1, base_price=500, active=True,
                  minimum_stay_months=0, maximum_stay_months=11,
                  tenant_gender_preference="female",
                  public_title="Habitación con baño privado", public_description="Descripción plantilla")
    duplicate = Room(property=target_property, code="Duplicate", display_order=2, base_price=600, active=True,
                     public_title="Habitación con baño privado")
    duplicate_two = Room(property=target_property, code="Duplicate2", display_order=3, base_price=600, active=True,
                         public_title="Habitación con baño privado (2)")
    old = Feature(slug="old-room", name="Antigua", scope="room", category="Room", display_order=1, active=True)
    copied = Feature(slug="copied-room", name="Copiada", scope="room", category="Room", display_order=2, active=True)
    inactive = Feature(slug="inactive-room", name="Inactiva", scope="room", category="Room", display_order=3, active=False)
    shared = Feature(slug="shared-property", name="Común compatible", scope="property", category="Property", display_order=1, active=True)
    foreign = Feature(slug="foreign-property", name="Solo origen", scope="property", category="Property", display_order=2, active=True)
    db_session.add_all([source_property, source, duplicate, duplicate_two, old, copied, inactive, shared, foreign]); db_session.flush()
    target.features.append(old)
    source.features.extend([copied, inactive])
    target_property.features.append(shared)
    source_property.features.extend([shared, foreign])
    source.public_highlights.extend([
        RoomPublicHighlight(feature_id=copied.id, position=0),
        RoomPublicHighlight(feature_id=foreign.id, position=1),
        RoomPublicHighlight(feature_id=shared.id, position=2),
    ])
    target.public_title = "No cambiar"; target.public_description = "Descripción"; target.square_meters = 12
    db_session.commit()

    response = client.post(
        f"/rooms/{target.id}/publication/copy-configuration",
        data={"source_room_id": source.id}, follow_redirects=False,
    )
    assert response.status_code == 303
    assert "success=room_configuration_copied" in response.headers["location"]
    assert "omitted=2" in response.headers["location"]
    db_session.expire_all()
    copied_target = db_session.get(Room, target.id)
    assert [feature.id for feature in copied_target.features] == [copied.id]
    assert [(item.feature_id, item.position) for item in copied_target.public_highlights] == [
        (copied.id, 0), (shared.id, 1)
    ]
    assert copied_target.property_id == target_property.id
    assert copied_target.base_price == 650 and copied_target.square_meters == 12
    assert copied_target.public_title == "Habitación con baño privado (3)"
    assert copied_target.public_description == "Descripción plantilla"
    assert copied_target.minimum_stay_months == 0 and copied_target.maximum_stay_months == 11
    assert copied_target.tenant_gender_preference == "female"
    assert copied_target.property.manager_id == target_property.manager_id


def test_copy_room_configuration_rolls_back_completely_on_commit_error(db_session, monkeypatch):
    prop, target = records(db_session)
    source = Room(property_id=prop.id, code="Source", display_order=2, base_price=500, active=True,
                  public_title="Nuevo título", public_description="Nueva descripción")
    old = Feature(slug="rollback-old", name="Anterior", scope="room", category="Room", display_order=1, active=True)
    new = Feature(slug="rollback-new", name="Nueva", scope="room", category="Room", display_order=2, active=True)
    db_session.add_all([source, old, new]); db_session.flush()
    target.features.append(old); source.features.append(new); db_session.commit()

    def fail_commit():
        raise RuntimeError("forced commit failure")

    monkeypatch.setattr(db_session, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="forced commit failure"):
        CommercialPublicationService().copy_room_configuration(db_session, target.id, source.id)
    db_session.expire_all()
    rolled_back = db_session.get(Room, target.id)
    assert [feature.id for feature in rolled_back.features] == [old.id]
    assert rolled_back.public_title is None and rolled_back.public_description is None


def test_copied_public_title_uses_first_available_numeric_suffix(db_session):
    prop, target = records(db_session)
    base = "Habitación luminosa"
    db_session.add(Room(property_id=prop.id, code="Used", display_order=2, base_price=500,
                        active=True, public_title=base))
    db_session.flush()
    service = CommercialPublicationService()
    assert service._available_copied_title(db_session, target, base) == f"{base} (2)"
    db_session.add(Room(property_id=prop.id, code="Used2", display_order=3, base_price=500,
                        active=True, public_title=f"{base} (2)"))
    db_session.flush()
    assert service._available_copied_title(db_session, target, base) == f"{base} (3)"


def test_minimum_stay_zero_is_configured_and_incompatible_range_is_rejected(db_session):
    _prop, room = records(db_session)
    service = CommercialPublicationService()
    missing = service.publication.assess_room(db_session, room.id)
    assert "room_minimum_stay_required" in missing.reasons
    saved = service.update_room(
        db_session, room.id, title="Habitación", description="Descripción",
        base_price="600", square_meters="12", minimum_stay_months="0",
        maximum_stay_months="", is_published=False, feature_ids=[],
    )
    assert saved.success and room.minimum_stay_months == 0
    assert "room_minimum_stay_required" not in service.publication.assess_room(db_session, room.id).reasons
    invalid = service.update_room(
        db_session, room.id, title="Habitación", description="Descripción",
        base_price="600", square_meters="12", minimum_stay_months="3",
        maximum_stay_months="2", is_published=False, feature_ids=[],
    )
    assert not invalid.success and invalid.message == "room_stay_range_invalid"
