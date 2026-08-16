from datetime import date

from backend.models.booking import Booking
from backend.models.property import Property
from backend.models.room import Room


def seed(client, db_session):
    property_obj = Property(name="Gantt Property", address="A", city="Madrid", owner="O", active=True)
    db_session.add(property_obj); db_session.flush()
    room = Room(property_id=property_obj.id, code="G-01", display_order=1, base_price=500, active=True)
    db_session.add(room); db_session.flush()
    booking = Booking(room_id=room.id, origin="manual", check_in=date(2026, 9, 1), check_out=date(2026, 9, 30), notes="private-note", price=500)
    db_session.add(booking); db_session.commit()
    return property_obj, room, booking


def test_page_contains_accessible_gantt_and_dedicated_assets(client, db_session):
    seed(client, db_session)
    response = client.get("/gantt/")
    assert response.status_code == 200
    assert 'id="ganttRoot"' in response.text
    assert 'aria-live="polite"' in response.text
    assert "/static/css/gantt.css" in response.text
    assert "/static/js/gantt.js" in response.text
    assert "<h2 id=\"ganttTitle\" class=\"mb-1\">Calendario</h2>" in response.text
    assert "Calendario de ocupación" not in response.text


def test_data_contract_filters_window_and_excludes_private_data(client, db_session):
    property_obj, room, booking = seed(client, db_session)
    response = client.get(f"/gantt/data?start=2026-09-01&end=2026-10-01&property_id={property_obj.id}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["window"]["start"] == "2026-09-01"
    assert payload["properties"][0]["rooms"][0]["id"] == room.id
    assert payload["properties"][0]["rooms"][0]["bookings"][0]["id"] == booking.id
    encoded = response.text
    for private in ("private-note", "external_reference", "price", "phone", "email", "import_url"):
        assert private not in encoded


def test_data_rejects_invalid_or_excessive_windows(client):
    assert client.get("/gantt/data?start=2026-09-01&end=2026-09-01").status_code == 400
    assert client.get("/gantt/data?start=2026-01-01&end=2027-01-03").status_code == 400
    assert client.get("/gantt/data?start=not-a-date&end=2026-01-03").status_code == 422


def test_frontend_uses_utc_offsets_and_half_open_widths():
    source = open("backend/static/js/gantt.js", encoding="utf-8").read()
    assert "Date.UTC" in source
    assert "getUTC" in source
    assert "visibleStart=Math.max(0,this.dayOffset(booking.check_in))" in source
    assert "visibleEnd=Math.min(this.data.window.day_count,this.dayOffset(booking.check_out))" in source
    assert "check_out + 1" not in source
    assert "Entrada:" in source and "Salida:" in source
    assert "event.target!==timeline||!room.active" in source


def test_gantt_scroll_is_confined_to_one_internal_viewport():
    source = open("backend/static/css/gantt.css", encoding="utf-8").read()
    assert "body.gantt-layout" in source
    assert ".gantt-main { width:0; min-width:0" in source
    assert "min-width:0" in source
    assert ".gantt-page { width:100%; max-width:100%" in source
    assert ".gantt-root { width:100%; max-width:100%" in source
    assert "overflow:auto" in source
    assert "flex:1 1 auto" in source
    assert ".gantt-canvas { width:max-content; min-width:100%" in source
    assert "max-height:calc" not in source
    template = open("backend/templates/pages/gantt.html", encoding="utf-8").read()
    assert "{% block body_class %}gantt-layout{% endblock %}" in template
    assert "{% block main_class %}gantt-main{% endblock %}" in template


def test_gantt_renders_continuous_room_list_without_property_rows():
    source = open("backend/static/js/gantt.js", encoding="utf-8").read()
    styles = open("backend/static/css/gantt.css", encoding="utf-8").read()
    assert "propertyRow" not in source
    assert "gantt-property-row" not in source
    assert "gantt-property-row" not in styles
    assert "gantt-room-identity" in source
    assert "gantt-room-details" in source
