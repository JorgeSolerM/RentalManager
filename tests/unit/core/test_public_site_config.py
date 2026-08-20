from pathlib import Path

from backend.core.config import get_public_site_base_url, get_public_site_name
from backend.core.media_storage import (
    ALLOWED_IMAGE_MIME_TYPES,
    MAX_IMAGE_UPLOAD_BYTES,
    MAX_IMAGE_PIXELS,
    PUBLIC_IMAGE_WIDTHS,
    MediaStoragePaths,
)


def test_public_site_configuration_is_explicit_and_safe(monkeypatch):
    monkeypatch.delenv("PUBLIC_SITE_BASE_URL", raising=False)
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
