from sqlalchemy import select

from backend.models.platform import Platform


def platform_data(**overrides) -> dict:
    data = {
        "name": "Booking.com",
        "slug": "booking",
        "supports_import": "true",
        "supports_export": "true",
    }
    data.update(overrides)
    return data


def test_platform_create_list_and_get_use_overridden_temporary_database(
    client, db_session
):
    create_response = client.post(
        "/settings/platforms/create",
        data=platform_data(),
        follow_redirects=False,
    )
    platform = db_session.scalar(select(Platform))
    list_response = client.get("/settings/platforms")
    get_response = client.get(f"/settings/platforms/edit/{platform.id}")

    assert create_response.status_code == 303
    assert create_response.headers["location"] == (
        "/settings/platforms?success=platform_created"
    )
    assert platform is not None
    assert list_response.status_code == 200
    assert "Booking.com" in list_response.text
    assert get_response.status_code == 200
    assert get_response.json() == {
        "id": platform.id,
        "name": "Booking.com",
        "slug": "booking",
        "supports_import": True,
        "supports_export": True,
        "active": True,
    }


def test_platform_update_delete_and_duplicate_error_use_overridden_temporary_database(
    client, db_session
):
    client.post("/settings/platforms/create", data=platform_data())
    platform = db_session.scalar(select(Platform))

    duplicate_response = client.post(
        "/settings/platforms/create",
        data=platform_data(name="Duplicada"),
        follow_redirects=False,
    )
    update_response = client.post(
        f"/settings/platforms/update/{platform.id}",
        data=platform_data(
            name="Airbnb",
            slug="airbnb",
            supports_import="false",
            supports_export="true",
        ),
        follow_redirects=False,
    )
    db_session.refresh(platform)
    delete_response = client.post(
        f"/settings/platforms/delete/{platform.id}",
        follow_redirects=False,
    )

    assert duplicate_response.status_code == 303
    assert duplicate_response.headers["location"] == (
        "/settings/platforms?error=slug_exists"
    )
    assert update_response.status_code == 303
    assert update_response.headers["location"] == (
        "/settings/platforms?success=platform_updated"
    )
    assert platform.name == "Airbnb"
    assert platform.slug == "airbnb"
    assert platform.supports_import is False
    assert platform.supports_export is True
    assert delete_response.status_code == 303
    assert delete_response.headers["location"] == (
        "/settings/platforms?success=platform_deleted"
    )
    assert db_session.get(Platform, platform.id) is None
