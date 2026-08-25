import re

from backend.models.property import Property
from backend.models.room import Room


def active_href(html: str) -> str:
    navigation = re.search(
        r'<nav[^>]+aria-label="Navegación principal"[^>]*>(.*?)</nav>',
        html,
        re.DOTALL,
    )
    assert navigation is not None
    match = re.search(
        r'<a href="([^"]+)" aria-current="page">', navigation.group(1)
    )
    assert match is not None
    assert navigation.group(1).count('aria-current="page"') == 1
    return match.group(1)


def test_sidebar_marks_dashboard_calendar_properties_and_settings(client):
    assert active_href(client.get("/").text) == "/"
    calendar_html = client.get("/gantt/").text
    assert active_href(calendar_html) == "/gantt/"
    assert '>Calendario</a>' in calendar_html
    assert '>Gantt</a>' not in calendar_html
    assert active_href(client.get("/properties/").text) == "/properties/"
    assert active_href(client.get("/settings/").text) == "/settings/"
    assert active_href(client.get("/settings/platforms").text) == "/settings/"


def test_room_routes_activate_properties_and_keep_context_heading(
    client, db_session
):
    property_obj = Property(
        name="Context Property", address="A", city="Madrid", owner="O", active=True
    )
    db_session.add(property_obj); db_session.flush()
    room = Room(
        property_id=property_obj.id, code="CTX-01", display_order=1,
        base_price=500, active=True,
    )
    db_session.add(room); db_session.commit()

    workspace = client.get(f"/rooms/{room.id}")
    listing = client.get(f"/rooms/property/{property_obj.id}")
    assert active_href(workspace.text) == "/properties/"
    assert active_href(listing.text) == "/properties/"
    assert "CTX-01" in workspace.text
    assert "Habitaciones - Context Property" in listing.text


def test_generic_page_titles_are_removed_but_browser_titles_remain(client):
    pages = {
        "/": r"<h[12][^>]*>\s*Dashboard\s*</h[12]>",
        "/gantt/": r"<h[12][^>]*>\s*(Calendario|Gantt)\s*</h[12]>",
        "/properties/": r"<h1[^>]*>\s*Propiedades\s*</h1>",
        "/settings/": r"<h1[^>]*>\s*Configuración\s*</h1>",
        "/settings/platforms": r"<h1[^>]*>\s*Plataformas\s*</h1>",
    }
    for path, redundant_heading in pages.items():
        html = client.get(path).text
        assert re.search(redundant_heading, html) is None
        assert "<title>" in html


def test_sidebar_active_state_has_hover_focus_and_non_color_cue():
    styles = open("backend/static/css/main.css", encoding="utf-8").read()
    sidebar = open(
        "backend/templates/components/sidebar.html", encoding="utf-8"
    ).read()
    assert ".sidebar-menu .active > a" in styles
    assert "border-left-color" in styles and "font-weight: 700" in styles
    assert ".sidebar-menu a:hover" in styles
    assert ".sidebar-menu a:focus-visible" in styles
    assert 'aria-current="page"' in sidebar
    assert "request.url.path" in sidebar


def test_desktop_layout_keeps_sidebar_in_viewport_and_main_scrollable():
    styles = open("backend/static/css/main.css", encoding="utf-8").read()
    base = open("backend/templates/layouts/base.html", encoding="utf-8").read()

    assert '@media (min-width: 769px)' in styles
    assert 'height: 100dvh' in styles
    assert '.app-shell' in styles and 'overflow: hidden' in styles
    assert '.sidebar {' in styles
    assert 'position: sticky' in styles
    assert 'overflow-y: auto' in styles
    assert 'max-height: 100%' in styles
    assert '.app-shell > main' in styles
    assert 'overflow: auto' in styles
    assert 'overflow-x: hidden' in styles
    assert '<div class="app-shell d-flex">' in base
    assert '{% include "components/sidebar.html" %}' in base


def test_global_sidebar_is_shared_by_long_content_sections(client):
    for path in ("/", "/properties/", "/gantt/", "/settings/", "/settings/platforms"):
        html = client.get(path).text
        assert 'class="app-shell d-flex"' in html
        assert 'class="sidebar"' in html
        assert html.count('aria-label="Navegación principal"') == 1


def test_product_and_manager_identity_live_only_in_the_header():
    sidebar = open(
        "backend/templates/components/sidebar.html", encoding="utf-8"
    ).read()
    header = open(
        "backend/templates/components/header.html", encoding="utf-8"
    ).read()

    assert "RentalManager" not in sidebar
    assert "HSI Rents" not in sidebar
    assert "RentalManager - HSI Rents" in header
    assert "sidebar-logo" not in sidebar


def test_settings_is_rendered_after_main_navigation_and_anchored_on_desktop():
    sidebar = open(
        "backend/templates/components/sidebar.html", encoding="utf-8"
    ).read()
    styles = open("backend/static/css/main.css", encoding="utf-8").read()

    primary_start = sidebar.index('class="sidebar-menu sidebar-menu-primary"')
    secondary_start = sidebar.index('class="sidebar-menu sidebar-menu-secondary"')
    assert primary_start < secondary_start
    primary = sidebar[primary_start:secondary_start]
    secondary = sidebar[secondary_start:]
    for label in ("Dashboard", "Calendario", "Propiedades"):
        assert label in primary
    assert "Plataformas" not in primary
    assert "Configuración" not in primary
    assert "Configuración" in secondary
    assert "path.startswith('/platforms')" in sidebar
    assert ".sidebar > .sidebar-menu-primary" in styles
    assert "margin-top: 1.75rem" in styles
    assert ".sidebar > .sidebar-menu-secondary" in styles
    assert "margin-top: auto" in styles
    assert "margin-bottom: .75rem" in styles
    assert "clamp(8rem, 24vh, 15rem)" not in styles
    assert "display: flex" in styles and "flex-direction: column" in styles
