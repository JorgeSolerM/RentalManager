const RMRoomCalendarActions = {
    labels: {
        save: "Guardando configuración…",
        sync: "Sincronizando calendario…"
    },

    start(form) {
        if (form.dataset.processing === "true") {
            return false;
        }

        const button = form.querySelector("[data-room-calendar-action-button]");
        if (!button) {
            return true;
        }

        form.dataset.processing = "true";
        form.setAttribute("aria-busy", "true");
        button.dataset.originalText = button.textContent.trim();
        button.disabled = true;
        button.innerHTML = [
            '<span class="spinner-border spinner-border-sm me-1" aria-hidden="true"></span>',
            this.labels[form.dataset.roomCalendarAction]
        ].join("");
        return true;
    },

    restore(form) {
        const button = form.querySelector("[data-room-calendar-action-button]");
        if (button && button.dataset.originalText) {
            button.textContent = button.dataset.originalText;
            delete button.dataset.originalText;
            button.disabled = false;
        }
        delete form.dataset.processing;
        form.removeAttribute("aria-busy");
    },

    initialize() {
        document.querySelectorAll("[data-room-calendar-action]").forEach((form) => {
            form.addEventListener("submit", (event) => {
                if (!this.start(form)) {
                    event.preventDefault();
                }
            });
        });
    },

    restoreAll() {
        document.querySelectorAll("[data-room-calendar-action]").forEach((form) => {
            this.restore(form);
        });
    }
};

document.addEventListener("DOMContentLoaded", () => {
    RMRoomCalendarActions.initialize();
});

window.addEventListener("pageshow", () => {
    RMRoomCalendarActions.restoreAll();
});
