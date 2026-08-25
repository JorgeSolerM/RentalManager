import os
from urllib.parse import urlsplit


APP_VERSION = "1.0.0"
DEFAULT_PUBLIC_SITE_NAME = "HSI Rents"


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


def get_public_site_base_url() -> str | None:
    """Return the configured public website origin, independent of Host."""
    value = os.getenv("PUBLIC_SITE_BASE_URL", "").strip().rstrip("/")
    if not value:
        return None
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        return None
    return value


def get_public_site_name() -> str:
    return os.getenv("PUBLIC_SITE_NAME", "").strip() or DEFAULT_PUBLIC_SITE_NAME


def get_public_site_allowed_hosts() -> list[str]:
    value = os.getenv("PUBLIC_SITE_ALLOWED_HOSTS", "").strip()
    if not value:
        return ["127.0.0.1", "localhost", "testserver"]
    return [host.strip() for host in value.split(",") if host.strip()]
