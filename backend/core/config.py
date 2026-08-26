import os
import re
from urllib.parse import urlsplit


APP_VERSION = "1.0.0"
DEFAULT_PUBLIC_SITE_NAME = "HSI Rents"
DEFAULT_PUBLIC_SITE_ALLOWED_HOSTS = ("127.0.0.1", "localhost", "testserver")
PUBLIC_HOST_PATTERN = re.compile(
    r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)(?:\.(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?))*$"
)


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
    """Return explicit public hosts plus safe local development hosts.

    The canonical hostname is trusted when PUBLIC_SITE_BASE_URL is valid. Extra
    aliases, such as ``www``, must be listed in PUBLIC_SITE_ALLOWED_HOSTS.
    Wildcards and host values containing schemes, paths or ports are rejected.
    """
    value = os.getenv("PUBLIC_SITE_ALLOWED_HOSTS", "").strip()
    candidates = list(DEFAULT_PUBLIC_SITE_ALLOWED_HOSTS)
    canonical = get_public_site_base_url()
    if canonical:
        canonical_host = urlsplit(canonical).hostname
        if canonical_host:
            candidates.append(canonical_host)
    candidates.extend(host.strip() for host in value.split(",") if host.strip())

    hosts: list[str] = []
    for candidate in candidates:
        host = candidate.lower().rstrip(".")
        if host == "*" or not PUBLIC_HOST_PATTERN.fullmatch(host):
            raise ValueError(
                "PUBLIC_SITE_ALLOWED_HOSTS must contain only explicit hostnames"
            )
        if host not in hosts:
            hosts.append(host)
    return hosts
