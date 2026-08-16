from __future__ import annotations

import re


GENERIC_BLOCK_LABELS = {
    "manualmente bloqueado",
    "bloqueado",
    "blocked",
    "reserved",
    "reservado",
    "manually blocked",
    "unavailable",
    "no disponible",
}
HOUSINGANYWHERE_RESERVATION = re.compile(
    r"^reservas\s*:\s*(?P<name>.+?)\s*$",
    re.IGNORECASE,
)
FLATIO_RESERVATION = re.compile(
    r"^Reserved by (?P<name>.+?) \(Flatio\)$",
)


def _normalize_spaces(value: str) -> str:
    return " ".join(value.split())


def extract_housinganywhere_guest_name(summary: str | None) -> str | None:
    if summary is None:
        return None
    normalized_summary = _normalize_spaces(summary)
    if not normalized_summary:
        return None
    if normalized_summary.casefold() in GENERIC_BLOCK_LABELS:
        return None

    match = HOUSINGANYWHERE_RESERVATION.fullmatch(normalized_summary)
    if match is None:
        return None
    name = _normalize_spaces(match.group("name"))
    if (
        not name
        or len(name) > 100
        or name.casefold() in GENERIC_BLOCK_LABELS
    ):
        return None
    return name


def extract_guest_name(platform_slug: str, summary: str | None) -> str | None:
    if platform_slug.casefold() == "housinganywhere":
        return extract_housinganywhere_guest_name(summary)
    if platform_slug.casefold() == "flatio" and summary is not None:
        normalized_summary = _normalize_spaces(summary)
        match = FLATIO_RESERVATION.fullmatch(normalized_summary)
        if match is not None:
            name = _normalize_spaces(match.group("name"))
            if (
                name
                and len(name) <= 100
                and name.casefold() not in GENERIC_BLOCK_LABELS
            ):
                return name
    return None
