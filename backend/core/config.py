import os
import re
from dataclasses import dataclass
from urllib.parse import urlsplit


APP_VERSION = "1.0.0"
DEFAULT_PUBLIC_SITE_NAME = "HSI Rents"
DEFAULT_PUBLIC_SITE_ALLOWED_HOSTS = ("127.0.0.1", "localhost", "testserver")
DEFAULT_PUBLIC_CONTACT_NAME = "Jorge Soler"
DEFAULT_PUBLIC_CONTACT_EMAIL = "jorgesoler@hsi-rents.com"
DEFAULT_PUBLIC_CONTACT_PHONE = "+34 647 427 935"
DEFAULT_PUBLIC_WHATSAPP_NUMBER = "+34 647 427 935"
DEFAULT_PUBLIC_LEGAL_HOLDER_NAME = "Jorge Soler Martínez"
DEFAULT_PUBLIC_LEGAL_NIF = "74233334Y"
DEFAULT_PUBLIC_LEGAL_ADDRESS = (
    "C/ Antonio Brotons Pastor, 31, bajo, 03205 Elche (Alicante)"
)
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


@dataclass(frozen=True)
class PublicContactConfig:
    name: str
    email: str
    phone: str
    whatsapp_number: str


@dataclass(frozen=True)
class PublicLegalConfig:
    holder_name: str
    nif: str
    address: str


def get_public_contact_config() -> PublicContactConfig:
    """Return deliberately public contact details with environment overrides."""
    return PublicContactConfig(
        name=os.getenv("PUBLIC_CONTACT_NAME", "").strip()
        or DEFAULT_PUBLIC_CONTACT_NAME,
        email=os.getenv("PUBLIC_CONTACT_EMAIL", "").strip()
        or DEFAULT_PUBLIC_CONTACT_EMAIL,
        phone=os.getenv("PUBLIC_CONTACT_PHONE", "").strip()
        or DEFAULT_PUBLIC_CONTACT_PHONE,
        whatsapp_number=os.getenv("PUBLIC_WHATSAPP_NUMBER", "").strip()
        or DEFAULT_PUBLIC_WHATSAPP_NUMBER,
    )


def get_public_legal_config() -> PublicLegalConfig:
    """Return the public legal identity without scattering it across templates."""
    return PublicLegalConfig(
        holder_name=os.getenv("PUBLIC_LEGAL_HOLDER_NAME", "").strip()
        or DEFAULT_PUBLIC_LEGAL_HOLDER_NAME,
        nif=os.getenv("PUBLIC_LEGAL_NIF", "").strip() or DEFAULT_PUBLIC_LEGAL_NIF,
        address=os.getenv("PUBLIC_LEGAL_ADDRESS", "").strip()
        or DEFAULT_PUBLIC_LEGAL_ADDRESS,
    )


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
