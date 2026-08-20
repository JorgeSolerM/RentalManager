from backend.models.feature import Feature
from backend.models.media_asset import MediaAsset
from backend.models.property import Property
from backend.models.property_photo import PropertyPhoto
from backend.models.room import Room


def records(db):
    prop = Property(name="Internal P", address="Secret address", city="Elche", owner="Private owner", active=True)
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
    response = client.post(f"/properties/{prop.id}/publication", data={
        "public_title": "Piso", "public_location": "Zona UMH",
        "public_slug": "piso", "is_published": "on",
    }, follow_redirects=False)
    assert response.status_code == 303 and "success=publication_saved" in response.headers["location"]
    db_session.refresh(prop)
    assert prop.is_published and prop.public_location == "Zona UMH"
    assert prop.public_description == "Valor legado que no se edita"


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
    page = client.get("/settings/")
    assert 'id="featuresTitle"' in page.text and "escritorio" in page.text
