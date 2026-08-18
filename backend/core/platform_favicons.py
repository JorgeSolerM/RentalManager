PLATFORM_FAVICONS = {
    "housinganywhere": "/static/icons/platforms/housinganywhere.svg",
    "flatio": "/static/icons/platforms/flatio.svg",
    "spotahome": "/static/icons/platforms/spotahome.png",
}


def platform_favicon(slug: str, configured_favicon: str | None = None) -> str | None:
    """Keep explicit Platform configuration authoritative over local defaults."""
    return configured_favicon or PLATFORM_FAVICONS.get(slug.casefold())
