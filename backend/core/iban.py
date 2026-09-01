import re


IBAN_PATTERN = re.compile(r"^[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}$")


def normalize_iban(value: str | None) -> str | None:
    canonical = re.sub(r"\s+", "", value or "").upper()
    return canonical or None


def is_valid_iban(value: str | None) -> bool:
    canonical = normalize_iban(value)
    if canonical is None or not IBAN_PATTERN.fullmatch(canonical):
        return False
    rearranged = canonical[4:] + canonical[:4]
    remainder = 0
    for character in rearranged:
        digits = character if character.isdigit() else str(ord(character) - 55)
        for digit in digits:
            remainder = (remainder * 10 + int(digit)) % 97
    return remainder == 1


def format_iban(value: str | None) -> str:
    canonical = normalize_iban(value) or ""
    return " ".join(
        canonical[index:index + 4]
        for index in range(0, len(canonical), 4)
    )


def mask_iban(value: str | None) -> str:
    canonical = normalize_iban(value)
    if not canonical:
        return ""
    masked = canonical[:2] + "•" * (len(canonical) - 6) + canonical[-4:]
    return " ".join(
        masked[index:index + 4]
        for index in range(0, len(masked), 4)
    )
