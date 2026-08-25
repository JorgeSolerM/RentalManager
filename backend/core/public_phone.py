import re
from urllib.parse import urlencode


PHONE_CHARACTERS = re.compile(r"^[+()\d\s.\-]+$")


def phone_link_values(value: str | None) -> tuple[str, str] | None:
    if not value:
        return None
    human = value.strip()
    if not human or not PHONE_CHARACTERS.fullmatch(human):
        return None
    digits = "".join(character for character in human if character.isdigit())
    if human.startswith("00"):
        digits = digits[2:]
        tel_number = f"+{digits}"
    elif human.startswith("+"):
        tel_number = f"+{digits}"
    else:
        tel_number = digits
    if not 6 <= len(digits) <= 15:
        return None
    return digits, f"tel:{tel_number}"


def whatsapp_url(phone: str | None, message: str) -> str | None:
    values = phone_link_values(phone)
    if values is None:
        return None
    digits, _tel_url = values
    return f"https://wa.me/{digits}?{urlencode({'text': message})}"
