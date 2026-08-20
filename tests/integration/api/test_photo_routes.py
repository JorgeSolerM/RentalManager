from io import BytesIO

from PIL import Image

from backend.api.routers import photos
from backend.core.image_processing import SafeImageProcessor
from backend.core.media_storage import MediaFileStore, MediaStoragePaths
from backend.models.property import Property
from backend.models.room import Room
from backend.services.photo_service import PhotoService, UploadPayload


def jpeg():
    output = BytesIO()
    Image.new("RGB", (400, 240), "navy").save(output, "JPEG")
    return output.getvalue()


def records(db):
    property_obj = Property(name="Casa", address="Privada", city="Madrid", owner="Owner", active=True)
    db.add(property_obj)
    db.flush()
    room = Room(property_id=property_obj.id, code="R01", display_order=1, base_price=700, active=True)
    db.add(room)
    db.commit()
    return property_obj, room


def test_admin_upload_gallery_variant_and_room_fallback(client, db_session, tmp_path, monkeypatch):
    property_obj, room = records(db_session)
    store = MediaFileStore(MediaStoragePaths.from_root(tmp_path / "media"))
    service = PhotoService(store=store, processor=SafeImageProcessor(store))
    monkeypatch.setattr(photos, "photo_service", service)

    response = client.post(
        f"/properties/{property_obj.id}/photos/upload",
        files=[("files", ("user-controlled.jpg", jpeg(), "image/jpeg"))],
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"].endswith("success=photos_uploaded")

    page = client.get(f"/properties/{property_obj.id}/photos")
    assert page.status_code == 200
    assert "Fotografías" in page.text and "Principal" in page.text
    asset_id = service.property_gallery(db_session, property_obj.id)[0].asset_id
    image = client.get(f"/media-assets/{asset_id}/variants/320")
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/webp"
    assert image.headers["x-content-type-options"] == "nosniff"

    room_page = client.get(f"/rooms/{room.id}?tab=configuracion")
    assert room_page.status_code == 200
    assert "Se utilizará como fallback la foto principal del inmueble" in room_page.text


def test_invalid_upload_redirects_with_domain_error(client, db_session, tmp_path, monkeypatch):
    property_obj, _ = records(db_session)
    store = MediaFileStore(MediaStoragePaths.from_root(tmp_path / "media"))
    monkeypatch.setattr(photos, "photo_service", PhotoService(store=store, processor=SafeImageProcessor(store)))
    response = client.post(
        f"/properties/{property_obj.id}/photos/upload",
        files=[("files", ("fake.png", b"not-image", "image/png"))],
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "error=media_invalid_image" in response.headers["location"]
    assert list(store.paths.temporary.iterdir()) == []


def test_photo_management_routes_are_admin_only_and_no_public_catalog_was_added(client):
    assert client.get("/public/rooms").status_code == 404
    assert client.get("/media-assets/1/variants/999").status_code == 404
    response = client.post(
        "/property-photos/1/primary",
        data={"return_to": "https://attacker.invalid"},
        follow_redirects=False,
    )
    assert response.status_code == 400


def test_reorder_endpoint_persists_exact_order(client, db_session, tmp_path, monkeypatch):
    property_obj, _ = records(db_session)
    store = MediaFileStore(MediaStoragePaths.from_root(tmp_path / "media"))
    service = PhotoService(store=store, processor=SafeImageProcessor(store))
    monkeypatch.setattr(photos, "photo_service", service)
    service.upload_property(
        db_session,
        property_obj.id,
        [UploadPayload(jpeg(), "image/jpeg")],
    )
    # A distinct second image.
    output = BytesIO(); Image.new("RGB", (400, 240), "red").save(output, "JPEG")
    service.upload_property(db_session, property_obj.id, [UploadPayload(output.getvalue(), "image/jpeg")])
    current = service.repository.list_property_photos(db_session, property_obj.id)
    wanted = [current[1].id, current[0].id]

    response = client.post(
        "/photo-order/property",
        json={"owner_id": property_obj.id, "photo_ids": wanted},
    )
    assert response.status_code == 200
    assert [photo.id for photo in service.repository.list_property_photos(db_session, property_obj.id)] == wanted
