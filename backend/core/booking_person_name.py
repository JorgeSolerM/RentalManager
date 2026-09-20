def booking_person_links(booking) -> list[dict]:
    """Only real, distinct Person links; never turn a channel name into an identity."""
    order = {'tenant': 0, 'occupant': 1, 'unclassified': 2, 'payer': 3, 'guarantor': 4}
    people = {}
    for party in sorted(getattr(booking, 'parties', None) or [], key=lambda p: (order.get(p.role, 99), p.id or 0)):
        people.setdefault(party.person_id, {'id': party.person_id, 'name': party.person.display_name or party.person.full_name})
    return list(people.values())


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
