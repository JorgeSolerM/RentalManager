from pathlib import Path

from backend.core.platform_favicons import PLATFORM_FAVICONS, platform_favicon


def test_priority_platforms_use_versioned_local_favicons():
    expected = {
        "housinganywhere": "/static/icons/platforms/housinganywhere.svg",
        "flatio": "/static/icons/platforms/flatio.svg",
        "spotahome": "/static/icons/platforms/spotahome.png",
    }

    assert PLATFORM_FAVICONS == expected
    for slug, public_path in expected.items():
        assert platform_favicon(slug) == public_path
        asset = Path("backend") / public_path.removeprefix("/")
        assert asset.is_file()
        assert asset.stat().st_size > 0


def test_explicit_platform_favicon_wins_and_unknown_platform_uses_fallback():
    assert platform_favicon("housinganywhere", "/custom/ha.svg") == "/custom/ha.svg"
    assert platform_favicon("future-platform") is None
