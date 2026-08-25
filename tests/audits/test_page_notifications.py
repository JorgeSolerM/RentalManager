from pathlib import Path


STATIC_ROOT = Path("backend/static")
PAGE_NOTIFICATION = (
    STATIC_ROOT / "services/rm_page_notification/rm_page_notification.js"
)


def test_page_notifications_are_centralized_and_loaded_before_page_scripts():
    base_template = Path("backend/templates/layouts/base.html").read_text(
        encoding="utf-8"
    )
    notification_position = base_template.index(
        "services/rm_page_notification/rm_page_notification.js"
    )
    scripts_block_position = base_template.index("{% block scripts %}")
    assert notification_position < scripts_block_position

    for script_name in ("properties.js", "rooms.js", "platforms.js", "bookings.js"):
        source = (STATIC_ROOT / "js" / script_name).read_text(encoding="utf-8")
        assert "RMPageNotification.show" not in source


def test_page_notification_registry_covers_existing_redirect_contracts():
    source = PAGE_NOTIFICATION.read_text(encoding="utf-8")
    expected_keys = {
        "property_updated",
        "property_deleted",
        "room_created",
        "room_updated",
        "room_deleted",
        "platform_created",
        "platform_updated",
        "platform_deleted",
        "booking_created",
        "booking_updated",
        "booking_deleted",
        "booking_guest_updated",
        "booking_external_block_deleted",
        "booking_overlap",
        "booking_room_inactive",
        "booking_guest_required",
        "booking_invalid_dates",
        "booking_invalid_price",
        "booking_imported_read_only",
        "booking_not_imported",
        "booking_external_block_still_present",
        "booking_external_block_presence_unknown",
        "booking_room_not_found",
        "room_calendar_created",
        "room_calendar_updated",
        "room_calendar_toggled",
        "room_calendar_deleted",
        "room_calendar_exists",
        "room_calendar_has_bookings",
        "room_calendar_sync_completed",
        "room_calendar_sync_completed_with_warnings",
        "room_calendar_sync_overlap",
        "room_calendar_sync_unsafe_url",
        "room_calendar_sync_invalid_feed",
        "room_calendar_sync_incompatible_stay",
        "room_calendar_sync_failed",
        "platform_capabilities_in_use",
    }
    for key in expected_keys:
        assert f"{key}:" in source

    assert 'document.addEventListener("DOMContentLoaded"' in source
    assert 'params.delete("success")' in source
    assert 'params.delete("error")' in source
    assert "history.replaceState" in source
    assert 'room_calendar_updated: "Configuración guardada."' in source
    assert (
        'room_calendar_sync_completed: "Calendario sincronizado correctamente."'
        in source
    )


def test_imported_booking_ui_only_enables_local_fields():
    source = (STATIC_ROOT / "js/bookings.js").read_text(encoding="utf-8")
    modal = Path("backend/templates/components/booking_modal.html").read_text(
        encoding="utf-8"
    )

    assert "/bookings/update-imported-local/" in source
    assert 'this.guestName.disabled = false' in source
    assert '[this.checkIn, this.checkOut, this.price, this.notes]' in source
    assert 'this.guestName.required = !readOnly' in source
    assert '"Guardar datos locales"' in source
    assert "externalBlockDeletable" in source
    assert '"Eliminar bloqueo"' in source
    assert 'this.form.action = `/bookings/delete/${this.bookingId}`' in source
    assert "bookingImportedNotice" in modal
    assert "únicamente pueden modificarse el huésped y las fechas previstas" in modal
    assert 'name="expected_arrival_date"' in modal
    assert 'name="expected_departure_date"' in modal


def test_room_calendar_actions_show_progress_and_prevent_duplicate_submits():
    source = (STATIC_ROOT / "js/room_calendar_actions.js").read_text(
        encoding="utf-8"
    )
    template = Path("backend/templates/pages/room_workspace.html").read_text(
        encoding="utf-8"
    )

    assert "Guardando configuración…" in source
    assert "Sincronizando calendario…" in source
    assert 'form.dataset.processing === "true"' in source
    assert "button.disabled = true" in source
    assert "spinner-border" in source
    assert 'window.addEventListener("pageshow"' in source
    assert 'data-room-calendar-action="save"' in template
    assert 'data-room-calendar-action="sync"' in template
    assert "js/room_calendar_actions.js" in template
