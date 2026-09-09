import re


SEPA_CREDITOR_IDENTIFIER_PATTERN = re.compile(
    r"^[A-Z]{2}[0-9]{2}[A-Z0-9]{3}[A-Z0-9]{1,28}$"
)
BIC_PATTERN = re.compile(r"^[A-Z]{6}[A-Z0-9]{2}(?:[A-Z0-9]{3})?$")


def normalize_sepa_identifier(value: str | None) -> str | None:
    normalized = re.sub(r"\s+", "", value or "").upper()
    return normalized or None


def is_valid_sepa_identifier(value: str | None) -> bool:
    normalized = normalize_sepa_identifier(value)
    return bool(normalized and SEPA_CREDITOR_IDENTIFIER_PATTERN.fullmatch(normalized))


def normalize_bic(value: str | None) -> str | None:
    normalized = re.sub(r"\s+", "", value or "").upper()
    return normalized or None


def is_valid_bic(value: str | None) -> bool:
    normalized = normalize_bic(value)
    return normalized is None or bool(BIC_PATTERN.fullmatch(normalized))
