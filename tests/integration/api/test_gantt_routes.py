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
    assert 'aria-label="Reservas por habitación"' in response.text
    assert ">Calendario</h2>" not in response.text
    assert "Calendario de ocupación" not in response.text
    assert 'data-view-months="8"' in response.text
    assert 'data-months="4"' in response.text
    assert 'data-months="8"' in response.text
    assert 'data-months="12"' in response.text


def test_page_scale_query_builds_four_and_twelve_month_windows(client, db_session):
    seed(client, db_session)
    four = client.get("/gantt/?view=4")
    annual = client.get("/gantt/?view=12")
    invalid = client.get("/gantt/?view=6")
    assert four.status_code == 200 and 'data-view-months="4"' in four.text
    assert annual.status_code == 200 and 'data-view-months="12"' in annual.text
    assert invalid.status_code == 422


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
    assert "MIN_MONTH_WIDTH: 84" in source
    assert "usable/this.months.length" in source
    assert "left=this.datePosition(visibleStart)" in source
    assert "width=this.datePosition(visibleEnd)-left" in source
    assert "check_out + 1" not in source
    assert "Entrada:" in source and "Salida:" in source
    assert "Number(this.root.dataset.viewMonths)||8" in source
    assert "[4,8,12].includes(months)" in source
    assert "this.shiftWindow(-1)" in source and "this.shiftWindow(1)" in source
    assert "s.getUTCMonth()+this.viewMonths" in source
    assert "loadDefault(){this.loadContextWindow(true);}" in source
    assert 'url.searchParams.set("view",String(this.viewMonths))' in source
    assert 'class="btn btn-outline-secondary gantt-view-button' in open("backend/templates/pages/gantt.html", encoding="utf-8").read()


def test_scale_state_survives_filters_and_navigation_in_frontend():
    source = open("backend/static/js/gantt.js", encoding="utf-8").read()
    assert "this.updateUrlView();" in source
    assert 'url.searchParams.set("property_id",this.propertyFilter.value)' in source
    assert 'url.searchParams.set("include_inactive","true")' in source
    assert "this.shiftWindow(-1)" in source and "this.shiftWindow(1)" in source


def test_all_scales_use_consecutive_single_month_navigation():
    source = open("backend/static/js/gantt.js", encoding="utf-8").read()
    template = open("backend/templates/pages/gantt.html", encoding="utf-8").read()
    assert 'data-months="{{ months }}"' in template
    assert "this.shiftWindow(-1)" in source
    assert "this.shiftWindow(1)" in source
    assert "this.viewMonths/2" not in source
    assert "s.setUTCMonth(s.getUTCMonth()+months)" in source
    assert "e.setUTCMonth(e.getUTCMonth()+months)" in source


def test_gantt_uses_compact_month_scale_and_progressive_bars():
    source = open("backend/static/js/gantt.js", encoding="utf-8").read()
    styles = open("backend/static/css/gantt.css", encoding="utf-8").read()
    assert "gantt-day" not in source and ".gantt-day" not in styles
    assert "gantt-week-marker" not in source and ".gantt-week-marker" not in styles
    assert "gantt-month-boundary" in source
    assert '"ene","feb","mar"' in source and '"ago","sept","oct"' in source
    assert "width>=220" in source and "width>=130" in source and "width>=65" in source
    assert "gantt-booking-minimal" in source
    assert "ResizeObserver" in source


def test_month_columns_have_uniform_width_and_daily_fraction_geometry():
    source = open("backend/static/js/gantt.js", encoding="utf-8").read()
    assert "width=`${this.monthWidth}px`" in source
    assert "left=`${index*this.monthWidth}px`" in source
    assert "dayIndex/month.days" in source
    assert "fraction*month.days+1e-9" in source
    assert "this.months.length*this.monthWidth" in source
    assert "pixelsPerDay" not in source


def test_booking_visual_inset_preserves_full_clickable_interval():
    source = open("backend/static/js/gantt.js", encoding="utf-8").read()
    styles = open("backend/static/css/gantt.css", encoding="utf-8").read()
    assert "inset=Math.min(1,paintedWidth/4)" in source
    assert "leftInset=booking.check_in<this.data.window.start?0:inset" in source
    assert "rightInset=booking.check_out>this.data.window.end?0:inset" in source
    assert "bar.style.cssText=`left:${left}px;width:${paintedWidth}px" in source
    assert "bar.append(visual)" in source
    assert ".gantt-booking-visual" in styles
    assert "left:var(--booking-inset-left)" in styles
    assert "right:var(--booking-inset-right)" in styles
    assert "pointer-events:none" in styles


def test_empty_timeline_is_not_a_booking_creation_target():
    source = open("backend/static/js/gantt.js", encoding="utf-8").read()
    styles = open("backend/static/css/gantt.css", encoding="utf-8").read()
    assert "openGap" not in source
    assert "openCreateModal" not in source
    assert 'timeline.addEventListener("click"' not in source
    assert "clientX" not in source
    assert "getBoundingClientRect" not in source
    assert "cursor:crosshair" not in styles
    assert ".gantt-booking" in styles and "cursor:pointer" in styles


def test_existing_bookings_and_rooms_remain_interactive():
    source = open("backend/static/js/gantt.js", encoding="utf-8").read()
    assert "BookingUI.openEditModal(booking.id,!booking.editable)" in source
    assert 'link.href=`/rooms/${room.id}`' in source


def test_room_hover_highlights_sticky_label_and_timeline_without_interaction():
    source = open("backend/static/js/gantt.js", encoding="utf-8").read()
    styles = open("backend/static/css/gantt.css", encoding="utf-8").read()
    assert ".gantt-room-row:hover .gantt-label" in styles
    assert ".gantt-room-row:hover .gantt-room-timeline" in styles
    assert "background-color:rgba(13,110,253,.055)" in styles
    assert ".gantt-label { position:sticky" in styles
    assert ".gantt-booking" in styles and "cursor:pointer" in styles
    assert "openGap" not in source
    assert 'timeline.addEventListener("click"' not in source


def test_room_workspace_remains_the_booking_creation_entry_point(client, db_session):
    _, room, _ = seed(client, db_session)
    response = client.get(f"/rooms/{room.id}")
    assert response.status_code == 200
    assert "+ Nueva reserva" in response.text
    assert 'data-bs-target="#bookingModal"' in response.text


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


def test_sync_indicator_is_only_rendered_for_attention_states():
    source = open("backend/static/js/gantt.js", encoding="utf-8").read()
    assert '["error","overdue","paused"].includes(room.sync.severity)' in source
    assert 'sync.textContent="⚠"' in source
    assert "gantt-sync-ok" not in source
