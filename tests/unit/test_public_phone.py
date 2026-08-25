from urllib.parse import parse_qs, urlsplit

from backend.core.public_phone import phone_link_values, whatsapp_url


def test_phone_normalization_supports_international_whatsapp_and_tel_links():
    assert phone_link_values("+34 (600) 123-123") == (
        "34600123123", "tel:+34600123123"
    )
    assert phone_link_values("0034 600 123 123") == (
        "34600123123", "tel:+34600123123"
    )
    assert phone_link_values("600 123 123") == (
        "600123123", "tel:600123123"
    )

    message = 'Hola, estoy interesado en la habitación "Habitación privada".\n\nhttps://example.test/habitaciones/room-1'
    result = whatsapp_url("+34 600 123 123", message)
    parsed = urlsplit(result)
    assert parsed.scheme == "https" and parsed.netloc == "wa.me"
    assert parsed.path == "/34600123123"
    assert parse_qs(parsed.query)["text"] == [message]
