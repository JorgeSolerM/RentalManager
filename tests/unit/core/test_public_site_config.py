from pathlib import Path

import pytest

from backend.core.config import (
    get_public_contact_config,
    get_public_legal_config,
    get_public_site_allowed_hosts,
    get_public_site_base_url,
    get_public_site_name,
)
from backend.core.media_storage import (
    ALLOWED_IMAGE_MIME_TYPES,
    MAX_IMAGE_UPLOAD_BYTES,
    MAX_IMAGE_PIXELS,
    PUBLIC_IMAGE_WIDTHS,
    MediaStoragePaths,
)


def test_public_site_configuration_is_explicit_and_safe(monkeypatch):
    monkeypatch.delenv("PUBLIC_SITE_BASE_URL", raising=False)
    monkeypatch.delenv("PUBLIC_SITE_ALLOWED_HOSTS", raising=False)
    monkeypatch.delenv("PUBLIC_SITE_NAME", raising=False)
    assert get_public_site_base_url() is None
    assert get_public_site_name() == "HSI Rents"

    monkeypatch.setenv("PUBLIC_SITE_BASE_URL", "https://rooms.example.com/")
    monkeypatch.setenv("PUBLIC_SITE_NAME", "  Public Brand  ")
    assert get_public_site_base_url() == "https://rooms.example.com"
    assert get_public_site_name() == "Public Brand"

    for unsafe in (
        "ftp://example.com",
        "https://user:pass@example.com",
        "https://example.com?token=secret",
    ):
        monkeypatch.setenv("PUBLIC_SITE_BASE_URL", unsafe)
        assert get_public_site_base_url() is None


def test_public_site_allowed_hosts_include_canonical_alias_and_local(monkeypatch):
    monkeypatch.setenv("PUBLIC_SITE_BASE_URL", "https://hsi-rents.com")
    monkeypatch.setenv(
        "PUBLIC_SITE_ALLOWED_HOSTS", "hsi-rents.com,www.hsi-rents.com"
    )

    assert get_public_site_allowed_hosts() == [
        "127.0.0.1",
        "localhost",
        "testserver",
        "hsi-rents.com",
        "www.hsi-rents.com",
    ]


def test_public_contact_configuration_has_safe_public_defaults_and_overrides(monkeypatch):
    for key in (
        "PUBLIC_CONTACT_NAME",
        "PUBLIC_CONTACT_EMAIL",
        "PUBLIC_CONTACT_PHONE",
        "PUBLIC_WHATSAPP_NUMBER",
    ):
        monkeypatch.delenv(key, raising=False)

    contact = get_public_contact_config()
    assert contact.name == "Jorge Soler"
    assert contact.email == "jorgesoler@hsi-rents.com"
    assert contact.phone == "+34 647 427 935"
    assert contact.whatsapp_number == "+34 647 427 935"

    monkeypatch.setenv("PUBLIC_CONTACT_NAME", "Nombre público")
    monkeypatch.setenv("PUBLIC_CONTACT_EMAIL", "contacto@example.com")
    monkeypatch.setenv("PUBLIC_CONTACT_PHONE", "+34 611 111 111")
    monkeypatch.setenv("PUBLIC_WHATSAPP_NUMBER", "+34 622 222 222")
    overridden = get_public_contact_config()
    assert overridden.name == "Nombre público"
    assert overridden.email == "contacto@example.com"
    assert overridden.phone == "+34 611 111 111"
    assert overridden.whatsapp_number == "+34 622 222 222"


def test_public_legal_identity_is_centralized_and_overridable(monkeypatch):
    for key in (
        "PUBLIC_LEGAL_HOLDER_NAME",
        "PUBLIC_LEGAL_NIF",
        "PUBLIC_LEGAL_ADDRESS",
    ):
        monkeypatch.delenv(key, raising=False)

    legal = get_public_legal_config()
    assert legal.holder_name == "Jorge Soler Martínez"
    assert legal.nif == "74233334Y"
    assert legal.address == (
        "C/ Antonio Brotons Pastor, 31, bajo, 03205 Elche (Alicante)"
    )

    monkeypatch.setenv("PUBLIC_LEGAL_HOLDER_NAME", "Titular de prueba")
    monkeypatch.setenv("PUBLIC_LEGAL_NIF", "00000000T")
    monkeypatch.setenv("PUBLIC_LEGAL_ADDRESS", "Domicilio de prueba")
    overridden = get_public_legal_config()
    assert overridden.holder_name == "Titular de prueba"
    assert overridden.nif == "00000000T"
    assert overridden.address == "Domicilio de prueba"


@pytest.mark.parametrize(
    "unsafe", ("*", "*.hsi-rents.com", "https://hsi-rents.com", "host:8001")
)
def test_public_site_allowed_hosts_reject_wildcards_and_non_hosts(
    monkeypatch, unsafe
):
    monkeypatch.delenv("PUBLIC_SITE_BASE_URL", raising=False)
    monkeypatch.setenv("PUBLIC_SITE_ALLOWED_HOSTS", unsafe)

    with pytest.raises(ValueError, match="explicit hostnames"):
        get_public_site_allowed_hosts()


def test_media_storage_configuration_creates_only_expected_directories(tmp_path):
    root = Path(tmp_path) / "media"
    paths = MediaStoragePaths.from_root(root)
    paths.ensure_directories()

    assert paths.root == root.resolve()
    assert paths.private.is_dir()
    assert paths.public.is_dir()
    assert paths.temporary.is_dir()
    assert MAX_IMAGE_UPLOAD_BYTES == 10 * 1024 * 1024
    assert MAX_IMAGE_PIXELS == 40_000_000
    assert ALLOWED_IMAGE_MIME_TYPES == {
        "image/jpeg", "image/png", "image/webp"
    }
    assert PUBLIC_IMAGE_WIDTHS == (320, 768, 1600)
