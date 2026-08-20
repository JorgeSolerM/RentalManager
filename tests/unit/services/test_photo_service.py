from io import BytesIO

from PIL import Image

from backend.core.image_processing import SafeImageProcessor
from backend.core.media_storage import MediaFileStore, MediaStoragePaths
from backend.models.media_asset import MediaAsset
from backend.models.property import Property
from backend.models.property_photo import PropertyPhoto
from backend.models.room import Room
from backend.models.room_photo import RoomPhoto
from backend.services.photo_service import PhotoService, UploadPayload


def upload(color, mime="image/jpeg"):
    output = BytesIO()
    Image.new("RGB", (500, 300), color).save(output, "JPEG")
    return UploadPayload(output.getvalue(), mime)


def setup_service(tmp_path):
    store = MediaFileStore(MediaStoragePaths.from_root(tmp_path / "media"))
    return PhotoService(store=store, processor=SafeImageProcessor(store)), store


def entities(db):
    property_obj = Property(name="P", address="A", city="C", owner="O", active=True)
    db.add(property_obj)
    db.flush()
    room = Room(property_id=property_obj.id, code="R1", display_order=1, base_price=500, active=True)
    db.add(room)
    db.commit()
    return property_obj, room


def test_first_photo_is_primary_and_reorder_is_consecutive(db_session, tmp_path):
    property_obj, _ = entities(db_session)
    service, _ = setup_service(tmp_path)
    assert service.upload_property(db_session, property_obj.id, [upload("red"), upload("blue"), upload("green")]).success

    photos = service.repository.list_property_photos(db_session, property_obj.id)
    assert [photo.position for photo in photos] == [0, 1, 2]
    assert [photo.is_primary for photo in photos] == [True, False, False]
    assert service.reorder(db_session, "property", photos[2].id, "up").success
    assert [photo.id for photo in service.repository.list_property_photos(db_session, property_obj.id)] == [photos[0].id, photos[2].id, photos[1].id]


def test_changes_primary_and_promotes_first_after_deletion(db_session, tmp_path):
    property_obj, _ = entities(db_session)
    service, store = setup_service(tmp_path)
    service.upload_property(db_session, property_obj.id, [upload("red"), upload("blue")])
    photos = service.repository.list_property_photos(db_session, property_obj.id)
    assert service.set_primary(db_session, "property", photos[1].id).success
    assert service.repository.get_property_photo(db_session, photos[1].id).is_primary
    deleted_key = photos[1].asset.storage_key

    assert service.delete_photo(db_session, "property", photos[1].id).success
    remaining = service.repository.list_property_photos(db_session, property_obj.id)
    assert len(remaining) == 1 and remaining[0].is_primary and remaining[0].position == 0
    assert not (store.paths.public / deleted_key).exists()


def test_can_mark_a_previously_primary_property_photo_again(db_session, tmp_path):
    property_obj, _ = entities(db_session)
    service, _ = setup_service(tmp_path)
    service.upload_property(db_session, property_obj.id, [upload("red"), upload("blue")])
    first, second = service.repository.list_property_photos(db_session, property_obj.id)

    assert service.set_primary(db_session, "property", second.id).success
    assert service.set_primary(db_session, "property", first.id).success
    photos = service.repository.list_property_photos(db_session, property_obj.id)
    assert [photo.id for photo in photos if photo.is_primary] == [first.id]


def test_current_primary_is_idempotent_without_commit(db_session, tmp_path, monkeypatch):
    property_obj, _ = entities(db_session)
    service, _ = setup_service(tmp_path)
    service.upload_property(db_session, property_obj.id, [upload("red")])
    primary = service.repository.list_property_photos(db_session, property_obj.id)[0]
    monkeypatch.setattr(db_session, "commit", lambda: (_ for _ in ()).throw(AssertionError("unexpected commit")))
    assert service.set_primary(db_session, "property", primary.id).success


def test_room_primary_switch_is_robust_and_unique(db_session, tmp_path):
    _, room = entities(db_session)
    service, _ = setup_service(tmp_path)
    service.upload_room(db_session, room.id, [upload("red"), upload("blue")])
    first, second = service.repository.list_room_photos(db_session, room.id)
    assert service.set_primary(db_session, "room", second.id).success
    assert service.set_primary(db_session, "room", first.id).success
    assert [photo.id for photo in service.repository.list_room_photos(db_session, room.id) if photo.is_primary] == [first.id]


def test_set_primary_rolls_back_to_previous_primary_on_commit_error(db_session, tmp_path, monkeypatch):
    property_obj, _ = entities(db_session)
    service, _ = setup_service(tmp_path)
    service.upload_property(db_session, property_obj.id, [upload("red"), upload("blue")])
    first, second = service.repository.list_property_photos(db_session, property_obj.id)
    original_commit = db_session.commit
    monkeypatch.setattr(db_session, "commit", lambda: (_ for _ in ()).throw(RuntimeError("commit failed")))
    try:
        try:
            service.set_primary(db_session, "property", second.id)
        except RuntimeError:
            pass
    finally:
        monkeypatch.setattr(db_session, "commit", original_commit)
    photos = service.repository.list_property_photos(db_session, property_obj.id)
    assert [photo.id for photo in photos if photo.is_primary] == [first.id]


def test_room_uses_property_primary_as_fallback_without_copy(db_session, tmp_path):
    property_obj, room = entities(db_session)
    service, _ = setup_service(tmp_path)
    service.upload_property(db_session, property_obj.id, [upload("red")])
    gallery = service.room_gallery(db_session, room.id)
    assert gallery.photos == ()
    assert gallery.fallback_photo is not None


def test_shared_asset_is_not_physically_deleted(db_session, tmp_path):
    property_obj, room = entities(db_session)
    service, store = setup_service(tmp_path)
    service.upload_property(db_session, property_obj.id, [upload("red")])
    property_photo = service.repository.list_property_photos(db_session, property_obj.id)[0]
    room_photo = RoomPhoto(room_id=room.id, media_asset_id=property_photo.asset.id, position=0, is_primary=True)
    db_session.add(room_photo)
    db_session.commit()
    key = property_photo.asset.storage_key

    assert service.delete_photo(db_session, "property", property_photo.id).success
    assert (store.paths.public / key / "320.webp").is_file()
    assert db_session.get(MediaAsset, room_photo.media_asset_id) is not None


def test_processing_rejection_rolls_back_all_uploads_and_cleans_files(db_session, tmp_path):
    property_obj, _ = entities(db_session)
    service, store = setup_service(tmp_path)
    bad = UploadPayload(b"broken", "image/jpeg")
    result = service.upload_property(db_session, property_obj.id, [upload("red"), bad])
    assert not result.success
    assert service.repository.list_property_photos(db_session, property_obj.id) == []
    assert db_session.query(MediaAsset).count() == 0
    assert list(store.paths.public.iterdir()) == []
    assert list(store.paths.temporary.iterdir()) == []


def test_duplicate_content_reuses_asset_but_not_within_same_owner(db_session, tmp_path):
    property_obj, room = entities(db_session)
    service, _ = setup_service(tmp_path)
    payload = upload("red")
    assert service.upload_property(db_session, property_obj.id, [payload]).success
    assert service.upload_room(db_session, room.id, [payload]).success
    assert db_session.query(MediaAsset).count() == 1
    assert db_session.query(PropertyPhoto).count() == 1
    assert db_session.query(RoomPhoto).count() == 1
    duplicate = service.upload_property(db_session, property_obj.id, [payload])
    assert not duplicate.success and duplicate.message == "media_duplicate_photo"
    assert db_session.query(PropertyPhoto).count() == 1


def test_failed_asset_is_not_used_as_room_fallback(db_session, tmp_path):
    property_obj, room = entities(db_session)
    service, _ = setup_service(tmp_path)
    service.upload_property(db_session, property_obj.id, [upload("red")])
    photo = service.repository.list_property_photos(db_session, property_obj.id)[0]
    photo.asset.status = "failed"
    db_session.commit()
    assert service.room_gallery(db_session, room.id).fallback_photo is None


def test_delete_rollback_restores_quarantined_files(db_session, tmp_path, monkeypatch):
    property_obj, _ = entities(db_session)
    service, store = setup_service(tmp_path)
    service.upload_property(db_session, property_obj.id, [upload("red")])
    photo = service.repository.list_property_photos(db_session, property_obj.id)[0]
    key = photo.asset.storage_key

    original_commit = db_session.commit
    monkeypatch.setattr(db_session, "commit", lambda: (_ for _ in ()).throw(RuntimeError("commit failed")))
    try:
        try:
            service.delete_photo(db_session, "property", photo.id)
        except RuntimeError:
            pass
    finally:
        monkeypatch.setattr(db_session, "commit", original_commit)

    assert (store.paths.public / key / "320.webp").is_file()
    assert service.repository.get_property_photo(db_session, photo.id) is not None


def test_gallery_query_count_is_constant(db_session, tmp_path):
    from sqlalchemy import event

    property_obj, _ = entities(db_session)
    service, _ = setup_service(tmp_path)
    service.upload_property(db_session, property_obj.id, [upload("red"), upload("blue"), upload("green")])
    property_id = property_obj.id
    count = 0

    def count_query(*_):
        nonlocal count
        count += 1

    event.listen(db_session.bind, "before_cursor_execute", count_query)
    try:
        gallery = service.property_gallery(db_session, property_id)
    finally:
        event.remove(db_session.bind, "before_cursor_execute", count_query)
    assert len(gallery) == 3
    assert count == 1


def test_exact_reorder_persists_for_property_and_room(db_session, tmp_path):
    property_obj, room = entities(db_session)
    service, _ = setup_service(tmp_path)
    service.upload_property(db_session, property_obj.id, [upload("red"), upload("blue"), upload("green")])
    service.upload_room(db_session, room.id, [upload("yellow"), upload("black")])
    property_photos = service.repository.list_property_photos(db_session, property_obj.id)
    room_photos = service.repository.list_room_photos(db_session, room.id)

    property_order = [property_photos[2].id, property_photos[0].id, property_photos[1].id]
    room_order = [room_photos[1].id, room_photos[0].id]
    assert service.reorder_exact(db_session, "property", property_obj.id, property_order).success
    assert service.reorder_exact(db_session, "room", room.id, room_order).success

    assert [photo.id for photo in service.repository.list_property_photos(db_session, property_obj.id)] == property_order
    assert [photo.position for photo in service.repository.list_property_photos(db_session, property_obj.id)] == [0, 1, 2]
    assert [photo.id for photo in service.repository.list_room_photos(db_session, room.id)] == room_order
    assert [photo.position for photo in service.repository.list_room_photos(db_session, room.id)] == [0, 1]


def test_exact_reorder_rejects_missing_duplicate_or_foreign_photos(db_session, tmp_path):
    first_property, room = entities(db_session)
    second_property = Property(name="P2", address="A", city="C", owner="O", active=True)
    db_session.add(second_property)
    db_session.commit()
    service, _ = setup_service(tmp_path)
    service.upload_property(db_session, first_property.id, [upload("red"), upload("blue")])
    service.upload_property(db_session, second_property.id, [upload("green")])
    photos = service.repository.list_property_photos(db_session, first_property.id)
    foreign = service.repository.list_property_photos(db_session, second_property.id)[0]

    assert not service.reorder_exact(db_session, "property", first_property.id, [photos[0].id]).success
    assert not service.reorder_exact(db_session, "property", first_property.id, [photos[0].id, photos[0].id]).success
    assert not service.reorder_exact(db_session, "property", first_property.id, [photos[0].id, foreign.id]).success
    assert [photo.id for photo in service.repository.list_property_photos(db_session, first_property.id)] == [photo.id for photo in photos]


def test_exact_reorder_rolls_back_on_commit_error(db_session, tmp_path, monkeypatch):
    property_obj, _ = entities(db_session)
    service, _ = setup_service(tmp_path)
    service.upload_property(db_session, property_obj.id, [upload("red"), upload("blue")])
    photos = service.repository.list_property_photos(db_session, property_obj.id)
    original_order = [photo.id for photo in photos]
    original_commit = db_session.commit
    monkeypatch.setattr(db_session, "commit", lambda: (_ for _ in ()).throw(RuntimeError("commit failed")))
    try:
        try:
            service.reorder_exact(db_session, "property", property_obj.id, list(reversed(original_order)))
        except RuntimeError:
            pass
    finally:
        monkeypatch.setattr(db_session, "commit", original_commit)
    assert [photo.id for photo in service.repository.list_property_photos(db_session, property_obj.id)] == original_order
