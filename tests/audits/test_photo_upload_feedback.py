from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_photo_form_has_accessible_selection_and_upload_feedback():
    template = (ROOT / "backend/templates/components/photo_gallery.html").read_text(encoding="utf-8")
    assert "Añadir imágenes" in template
    assert "Subir imágenes" not in template
    assert "data-photo-submit" not in template
    assert "data-photo-selection-list" in template
    assert 'aria-live="polite"' in template
    assert "multiple" in template


def test_photo_selection_starts_limited_queue_and_prevents_double_upload():
    script = (ROOT / "backend/static/js/photo_upload.js").read_text(encoding="utf-8")
    assert "Array.from(input.files" in script
    assert "file.name" in script
    assert "void runQueue(files)" in script
    assert "PHOTO_UPLOAD_CONCURRENCY = 3" in script
    assert "if (running" in script
    assert 'setAttribute("aria-disabled"' in script
    assert 'form.toggleAttribute("aria-busy"' in script
    assert 'input.value = ""' in script


def test_individual_and_partial_error_states_are_present():
    script = (ROOT / "backend/static/js/photo_upload.js").read_text(encoding="utf-8")
    assert 'pending: ["○", "Pendiente"]' in script
    assert 'uploading: ["○", "Subiendo"]' in script
    assert 'completed: ["✓", "Completado"]' in script
    assert 'error: ["⚠", "Error al subir"]' in script
    assert 'entry.status = "completed"' in script
    assert 'entry.status = "error"' in script
    assert "Promise.all" in script
    assert "con error" in script
    assert 'createElement(entry.status === "completed" ? "strong" : "span")' in script
    assert 'className = "rm-photo-upload-icon"' in script


def test_photo_cards_hide_actions_until_selected_and_support_drag_and_keyboard():
    template = (ROOT / "backend/templates/components/photo_gallery.html").read_text(encoding="utf-8")
    script = (ROOT / "backend/static/js/photo_gallery.js").read_text(encoding="utf-8")
    css = (ROOT / "backend/static/css/main.css").read_text(encoding="utf-8")
    assert 'aria-selected="false"' in template
    assert 'draggable="true"' in template
    assert "Mover fotografía hacia arriba" not in template
    assert "Mover fotografía hacia abajo" not in template
    assert "Guardar orden" not in template and "Guardar orden" not in script
    assert ".rm-photo-actions-panel {" in css
    assert "height: 3.35rem" in css
    assert '.rm-photo-card[aria-selected="true"] .rm-photo-actions' in css
    assert "opacity: 0" in css and "opacity: 1" in css
    assert "150ms" in css
    assert "prefers-reduced-motion: reduce" in css
    assert 'aria-label="Eliminar fotografía"' in template
    assert 'title="Eliminar fotografía"' in template
    assert "rm-photo-primary-badge" in template and "position: absolute" in css
    assert "rm-photo-card-body" not in template
    assert 'gallery.addEventListener("dragstart"' in script
    assert 'gallery.addEventListener("drop"' in script
    assert 'gallery.addEventListener("keydown"' in script
    assert "Alt y las flechas" in template
    assert "restore(previousOrder)" in script
    assert "RMNotification.error" in script
    assert script.count("fetch(") == 1
    assert "suppressClickUntil" in script
    assert "Guardando…" in script
    assert "rm-photo-card-insert-before" in script
    assert "rm-photo-card-insert-after" in script
    assert "nearestCard" in script
    assert 'event.clientY < rect.top ? "before"' in script
    assert 'event.clientY > rect.bottom ? "after"' in script
    assert "insertion.target[insertion.position](dragged)" in script
    assert script.index("insertion.target[insertion.position](dragged)") < script.index("await persist(snapshot)")


def test_both_management_pages_load_shared_upload_behavior():
    property_page = (ROOT / "backend/templates/pages/property_photos.html").read_text(encoding="utf-8")
    room_page = (ROOT / "backend/templates/pages/room_workspace.html").read_text(encoding="utf-8")
    assert "js/photo_upload.js" in property_page
    assert "js/photo_upload.js" in room_page
