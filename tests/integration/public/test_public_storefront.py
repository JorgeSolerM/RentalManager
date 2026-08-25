from datetime import date
import html
import re
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from backend.core.media_storage import MediaFileStore, MediaStoragePaths
from backend.models.booking import Booking
from backend.models.feature import Feature
from backend.models.media_asset import MediaAsset
from backend.models.manager import Manager
from backend.models.property import Property
from backend.models.property_photo import PropertyPhoto
from backend.models.room import Room
from backend.models.room_photo import RoomPhoto
from backend.models.room_public_highlight import RoomPublicHighlight
from backend.models.rental_requirement import RentalRequirement
from backend.public.app_factory import create_public_app
from backend.public.database import get_public_db
from backend.public.service import PublicRoomService


TODAY = date(2026, 8, 21)


@pytest.fixture
def public_context(db_session, tmp_path, monkeypatch):
    store = MediaFileStore(MediaStoragePaths.from_root(tmp_path / "media"))
    app = create_public_app(media_store=store)

    def override_db():
        yield db_session

    app.dependency_overrides[get_public_db] = override_db
    monkeypatch.setattr("backend.public.service.business_today", lambda: TODAY)
    with TestClient(app) as client:
        yield client, store


def add_ready_asset(db, store, key: str) -> MediaAsset:
    asset = MediaAsset(
        storage_key=key,
        mime_type="image/webp",
        width=1600,
        height=1000,
        byte_size=10,
        checksum_sha256=key * 2,
        status="ready",
    )
    db.add(asset)
    db.flush()
    for width in (320, 768, 1600):
        path = store.asset_file(key, width)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"RIFF-test-WEBP")
    return asset


def add_public_room(db, store, *, code="R01", slug="room-one"):
    manager = Manager(name="Gestora Demo", active=True)
    db.add(manager)
    db.flush()
    property_obj = Property(
        name="Internal property",
        address="Private street 42",
        street="Solars",
        street_number="10",
        floor="entlo",
        door="A",
        city="Internal city",
        owner="Private owner",
        notes="Private property notes",
        active=True,
        public_title="Shared home",
        public_location="Zona UMH · Elche",
        public_slug="shared-home",
        is_published=True,
        manager_id=manager.id,
    )
    db.add(property_obj)
    db.flush()
    room = Room(
        property_id=property_obj.id,
        code=code,
        display_order=1,
        base_price=650,
        square_meters=12,
        minimum_stay_months=0,
        maximum_stay_months=None,
        active=True,
        public_title="Habitación luminosa",
        public_description="Dormitorio exterior, cómodo y tranquilo.",
        public_slug=slug,
        is_published=True,
    )
    db.add(room)
    db.flush()
    room_feature = Feature(
        slug=f"desk-{slug}", name="Escritorio", scope="room",
        category="Habitación", display_order=1, active=True,
    )
    bed_feature = Feature(
        slug="cama-individual", name="Cama individual", scope="room",
        category="Dormitorio", display_order=0, active=True,
    )
    property_feature = Feature(
        slug=f"wifi-{slug}", name="Wi-Fi", scope="property",
        category="Comunes", display_order=1, active=True,
    )
    db.add_all([bed_feature, room_feature, property_feature])
    db.flush()
    room.features.extend([bed_feature, room_feature])
    property_obj.features.append(property_feature)
    room_asset = add_ready_asset(db, store, "a" * 32)
    property_asset = add_ready_asset(db, store, "b" * 32)
    db.add_all([
        RoomPhoto(
            room_id=room.id, media_asset_id=room_asset.id,
            position=0, is_primary=True,
        ),
        PropertyPhoto(
            property_id=property_obj.id, media_asset_id=property_asset.id,
            position=0, is_primary=True,
        ),
    ])
    db.commit()
    return property_obj, room


def test_detail_calculates_flatmates_from_eligible_sibling_bed_capacity(
    public_context, db_session
):
    client, store = public_context
    property_obj, room = add_public_room(db_session, store)
    double_bed = Feature(
        slug="cama-doble", name="Cama doble", scope="room",
        category="Dormitorio", display_order=0, active=True,
    )
    individual_bed = db_session.query(Feature).filter_by(
        slug="cama-individual"
    ).one()
    db_session.add(double_bed)
    db_session.flush()

    def sibling(code, slug, bed):
        item = Room(
            property_id=property_obj.id, code=code, display_order=2,
            base_price=600, minimum_stay_months=0, active=True,
            public_title=code, public_description="Descripción pública suficiente.",
            public_slug=slug, is_published=True, features=[bed],
        )
        db_session.add(item)
        return item

    double_room = sibling("R02", "room-two", double_bed)
    sibling("R03", "room-three", individual_bed)
    db_session.commit()

    response = client.get(f"/habitaciones/{room.public_slug}")
    assert response.status_code == 200
    assert "3 compañeros de piso" in response.text

    double_room.is_published = False
    db_session.commit()
    response = client.get(f"/habitaciones/{room.public_slug}")
    assert "1 compañero de piso" in response.text


@pytest.mark.parametrize(
    ("preference", "public_label"),
    [(None, "Mixto"), ("any", "Mixto"), ("male", "Solo chicos"), ("female", "Solo chicas")],
)
def test_detail_renders_public_tenant_gender_label(
    public_context, db_session, preference, public_label
):
    client, store = public_context
    _, room = add_public_room(db_session, store)
    room.tenant_gender_preference = preference
    db_session.commit()
    response = client.get(f"/habitaciones/{room.public_slug}")
    assert public_label in response.text
    assert "Preferencia de inquilino" not in response.text


def test_detail_exposes_only_configured_public_rules_and_active_requirements(
    public_context, db_session
):
    client, store = public_context
    property_obj, room = add_public_room(db_session, store)
    identity = RentalRequirement(
        slug="identity-document",
        public_name="Documento de identidad",
        public_description="Documento vigente.",
        active=True,
        display_order=20,
    )
    inactive = RentalRequirement(
        slug="internal-inactive",
        public_name="Requisito interno oculto",
        active=False,
        display_order=10,
    )
    db_session.add_all([identity, inactive])
    db_session.flush()
    property_obj.smoking_allowed = False
    property_obj.pets_allowed = True
    property_obj.minimum_tenant_age = 18
    property_obj.maximum_tenant_age = 48
    property_obj.requirements.extend([inactive, identity])
    db_session.commit()

    dto = PublicRoomService().get_room(db_session, room.public_slug, today=TODAY)
    response = client.get(f"/habitaciones/{room.public_slug}")

    assert [rule.label for rule in dto.housing_rules] == [
        "No se permite fumar",
        "Se permiten mascotas",
        "No se admiten parejas",
    ]
    assert dto.tenant_age.model_dump() == {"minimum": 18, "maximum": 48}
    assert [item.model_dump() for item in dto.requirements] == [
        {"name": "Documento de identidad", "description": "Documento vigente."}
    ]
    assert "Normas y condiciones" in response.text
    assert "Edad admitida: de 18 a 48 años" in response.text
    assert "Requisito interno oculto" not in response.text
    assert "identity-document" not in response.text


def test_couples_rule_is_derived_once_from_room_bed_type(public_context, db_session):
    _client, store = public_context
    _property_obj, room = add_public_room(db_session, store)

    individual = PublicRoomService().get_room(db_session, room.public_slug, today=TODAY)
    individual_labels = [rule.label for rule in individual.housing_rules]
    assert individual_labels.count("No se admiten parejas") == 1
    assert "Se admiten parejas" not in individual_labels

    bed = next(feature for feature in room.features if feature.slug == "cama-individual")
    bed.slug = "cama-doble"
    bed.name = "Cama doble"
    db_session.commit()

    double = PublicRoomService().get_room(db_session, room.public_slug, today=TODAY)
    double_labels = [rule.label for rule in double.housing_rules]
    assert double_labels.count("Se admiten parejas") == 1
    assert "No se admiten parejas" not in double_labels


def test_catalog_exposes_only_rooms_that_are_really_publicable(
    public_context, db_session
):
    client, store = public_context
    property_obj, room = add_public_room(db_session, store)

    statements = []
    def capture(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement.lower())
    event.listen(db_session.bind, "before_cursor_execute", capture)
    try:
        response = client.get("/")
    finally:
        event.remove(db_session.bind, "before_cursor_execute", capture)
    assert response.status_code == 200
    assert room.public_title in response.text
    assert property_obj.public_location in response.text
    assert len(statements) <= 7
    public_sql = "\n".join(statements)
    for private_column in (
        "properties.address", "properties.owner", "properties.notes",
        "rooms.master_calendar_token", "bookings.guest_id",
        "bookings.external_reference", "bookings.notes", "bookings.ical_uid",
    ):
        assert private_column not in public_sql
    assert "room_calendars" not in public_sql and "guests" not in public_sql

    room.is_published = False
    db_session.commit()
    assert room.public_title not in client.get("/").text

    room.is_published = True
    property_obj.is_published = False
    db_session.commit()
    assert room.public_title not in client.get("/").text

    property_obj.is_published = True
    property_obj.active = False
    db_session.commit()
    assert room.public_title not in client.get("/").text


def test_catalog_and_detail_use_only_ordered_room_public_highlights(
    public_context, db_session
):
    client, store = public_context
    property_obj, room = add_public_room(db_session, store)
    room_feature = next(feature for feature in room.features if feature.name == "Escritorio")
    property_feature = property_obj.features[0]

    without_highlights = client.get("/").text
    assert "Escritorio" not in without_highlights
    assert "Wi-Fi" not in without_highlights

    db_session.add_all([
        RoomPublicHighlight(room_id=room.id, feature_id=property_feature.id, position=0),
        RoomPublicHighlight(room_id=room.id, feature_id=room_feature.id, position=1),
    ])
    db_session.commit()
    db_session.expire_all()

    catalog = client.get("/").text
    detail = client.get(f"/habitaciones/{room.public_slug}").text
    assert catalog.index("Wi-Fi") < catalog.index("Escritorio")
    assert detail.index("Wi-Fi") < detail.index("Escritorio")

def test_room_detail_uses_effective_gallery_features_and_derived_availability(
    public_context, db_session
):
    client, store = public_context
    _, room = add_public_room(db_session, store)
    db_session.add(
        Booking(
            room_id=room.id,
            origin="manual",
            check_in=date(2026, 8, 1),
            check_out=date(2026, 9, 1),
            notes="Private booking notes",
        )
    )
    db_session.commit()

    response = client.get(f"/habitaciones/{room.public_slug}")
    assert response.status_code == 200
    assert "Disponible desde 01/09/2026" in response.text
    assert "Características" in response.text
    assert "Habitación" in response.text and "Escritorio" in response.text
    assert "Comunes" in response.text and "Wi-Fi" in response.text
    assert response.text.count('data-gallery-slide') == 2
    assert 'aria-label="Imagen anterior"' in response.text
    assert 'aria-label="Imagen siguiente"' in response.text
    assert 'data-gallery-open' in response.text
    assert 'role="dialog"' in response.text
    assert 'aria-modal="true"' in response.text
    assert 'data-lightbox-counter' in response.text
    assert 'aria-label="Cerrar galería"' in response.text
    assert "original.webp" not in response.text
    assert 'class="detail-sidebar"' in response.text
    assert response.text.index("a" * 32) < response.text.index("b" * 32)
    assert "Private street" not in response.text
    assert "Private owner" not in response.text
    assert "Private booking notes" not in response.text
    assert "Gestora Demo" in response.text
    assert "Sin estancia mínima" in response.text and "Sin límite" in response.text

    dto = PublicRoomService().get_room(db_session, room.public_slug, today=TODAY)
    serialized = dto.model_dump_json()
    for forbidden in (
        "guest", "booking", "platform", "room_calendar", "external_reference",
        "ical", "owner", "notes", "address",
    ):
        assert forbidden not in serialized.lower()


def test_shared_bathroom_counts_render_with_plural_and_private_bathroom_independently(
    public_context, db_session
):
    client, store = public_context
    property_obj, room = add_public_room(db_session, store)
    private_bathroom = Feature(
        slug="bano-privado", name="Baño privado", scope="room",
        category="Privado", display_order=2, active=True,
    )
    db_session.add(private_bathroom)
    room.features.append(private_bathroom)
    property_obj.shared_full_bathroom_count = 1
    property_obj.shared_toilet_count = 2
    db_session.commit()
    db_session.expire_all()

    response = client.get(f"/habitaciones/{room.public_slug}")
    assert response.status_code == 200
    assert "Baño privado" in response.text
    assert "1 baño completo compartido" in response.text
    assert "2 aseos compartidos" in response.text

    property_obj = db_session.get(Property, property_obj.id)
    property_obj.shared_full_bathroom_count = 0
    property_obj.shared_toilet_count = 0
    db_session.commit()
    db_session.expire_all()
    zero_response = client.get(f"/habitaciones/{room.public_slug}")
    assert "baños completos compartidos" not in zero_response.text
    assert "aseos compartidos" not in zero_response.text

    property_obj = db_session.get(Property, property_obj.id)
    property_obj.shared_full_bathroom_count = None
    property_obj.shared_toilet_count = None
    db_session.commit()
    db_session.expire_all()
    null_response = client.get(f"/habitaciones/{room.public_slug}")
    assert "baño completo compartido" not in null_response.text
    assert "aseo compartido" not in null_response.text


def test_room_detail_builds_map_from_structured_address_only(
    public_context, db_session
):
    client, store = public_context
    property_obj, room = add_public_room(db_session, store)

    response = client.get(f"/habitaciones/{room.public_slug}")
    assert response.status_code == 200
    assert "https://www.google.com/maps/search/?api=1&amp;query=Solars+10%2C+Internal+city" in response.text
    assert 'target="_blank"' in response.text
    assert 'rel="noopener noreferrer"' in response.text
    assert "Private street 42" not in response.text
    assert "entlo" not in response.text
    assert "query=Solars+10%2C+Internal+city" in response.text

    property_obj.street_number = None
    db_session.commit()
    without_number = client.get(f"/habitaciones/{room.public_slug}")
    assert "query=Solars%2C+Internal+city" in without_number.text

    property_obj.street = None
    db_session.commit()
    without_street = client.get(f"/habitaciones/{room.public_slug}")
    assert without_street.status_code == 200
    assert "Ver en el mapa" not in without_street.text
    assert "google.com/maps" not in without_street.text


def test_room_contact_uses_property_manager_phone_and_configured_public_url(
    public_context, db_session, monkeypatch
):
    client, store = public_context
    property_obj, room = add_public_room(db_session, store)
    property_obj.manager.phone = "+34 600 123-123"
    db_session.commit()
    monkeypatch.setenv("PUBLIC_SITE_BASE_URL", "https://www.hsi-rents.com")

    response = client.get(f"/habitaciones/{room.public_slug}")
    match = re.search(r'class="whatsapp-contact" href="([^"]+)"', response.text)
    assert match is not None
    parsed = urlsplit(html.unescape(match.group(1)))
    assert parsed.netloc == "wa.me" and parsed.path == "/34600123123"
    message = parse_qs(parsed.query)["text"][0]
    assert room.public_title in message
    assert message.endswith(f"https://www.hsi-rents.com/habitaciones/{room.public_slug}")
    assert "\n\n" in message

    property_obj.manager.phone = None
    db_session.commit()
    assert "Contactar por WhatsApp" not in client.get(
        f"/habitaciones/{room.public_slug}"
    ).text


def test_effective_features_are_grouped_deduplicated_and_unknown_categories_fallback(
    public_context, db_session
):
    _client, store = public_context
    property_obj, room = add_public_room(db_session, store)
    shared = Feature(
        slug="shared-unknown", name="Característica compartida", scope="both",
        category="Categoría futura", display_order=7, active=True,
    )
    db_session.add(shared)
    db_session.flush()
    room.features.append(shared)
    property_obj.features.append(shared)
    db_session.commit()

    dto = PublicRoomService().get_room(db_session, room.public_slug, today=TODAY)
    groups = {group.category: group for group in dto.feature_groups}
    assert [feature.name for feature in groups["Categoría futura"].features] == [
        "Característica compartida"
    ]
    assert groups["Categoría futura"].icon_url.endswith("/generic.svg")


def test_public_availability_uses_room_minimum_stay_configuration(public_context, db_session):
    client, store = public_context
    _, room = add_public_room(db_session, store)
    db_session.add(Booking(room_id=room.id, origin="manual", check_in=date(2026, 10, 1), check_out=date(2026, 10, 15)))
    db_session.commit()
    response = client.get(f"/habitaciones/{room.public_slug}")
    assert "Disponible del 21/08/2026 al 30/09/2026" in response.text


def test_non_publicable_detail_is_always_not_found(public_context, db_session):
    client, store = public_context
    property_obj, room = add_public_room(db_session, store)
    assert client.get(f"/habitaciones/{room.public_slug}").status_code == 200

    room.base_price = None
    db_session.commit()
    assert client.get(f"/habitaciones/{room.public_slug}").status_code == 404

    room.base_price = 650
    property_obj.is_published = False
    db_session.commit()
    assert client.get(f"/habitaciones/{room.public_slug}").status_code == 404
    assert client.get("/habitaciones/does-not-exist").status_code == 404


def test_public_media_serves_only_ready_derivatives_and_rejects_unsafe_paths(
    public_context, db_session
):
    client, store = public_context
    _, room = add_public_room(db_session, store)
    key = room.photos[0].asset.storage_key

    response = client.get(f"/media/{key}/768.webp")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/webp"
    assert "immutable" in response.headers["cache-control"]
    assert client.head(f"/media/{key}/768.webp").status_code == 200
    assert client.get(f"/media/{key}/999.webp").status_code == 404
    assert client.get(f"/media/{key}/original.webp").status_code == 404
    assert client.get("/media/private/original.webp").status_code == 404
    assert client.get("/media/tmp/320.webp").status_code == 404
    assert client.get("/media/%2e%2e/320.webp").status_code == 404


def test_public_app_has_security_headers_no_schema_and_no_write_routes(
    public_context,
):
    client, _store = public_context
    response = client.get("/")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404
    assert client.post("/").status_code == 405
    assert client.get("/", headers={"host": "untrusted.example"}).status_code == 400
