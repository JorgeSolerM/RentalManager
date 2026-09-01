def booking_person_name(booking) -> str:
    """Return a useful operational label across ORM and lightweight DTO tests."""
    value = getattr(booking, "operational_person_name", None)
    if value:
        return value
    source = getattr(booking, "source_guest_name", None)
    if source:
        return source
    guest = getattr(booking, "guest", None)
    if guest is not None:
        return getattr(guest, "display_name", None) or guest.full_name
    return "Huésped desconocido"
