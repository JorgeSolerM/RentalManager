import os
from urllib.parse import urlsplit


def get_public_base_url() -> str | None:
    """Return the explicitly configured public origin, never the request Host."""
    value = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")
    if not value:
        return None
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        return None
    return value
