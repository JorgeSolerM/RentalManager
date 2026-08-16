document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("[data-master-calendar-url]").forEach((button) => {
        button.addEventListener("click", async () => {
            try {
                await navigator.clipboard.writeText(button.dataset.masterCalendarUrl);
                RMNotification.success("URL del calendario copiada.");
            } catch (_error) {
                RMNotification.error("No se pudo copiar la URL del calendario.");
            }
        });
    });

    const regenerationForm = document.querySelector("[data-master-calendar-regenerate]");
    if (regenerationForm) {
        regenerationForm.addEventListener("submit", (event) => {
            const accepted = window.confirm(
                "La URL actual dejará de funcionar inmediatamente. Tendrás que actualizarla en todas las plataformas. ¿Continuar?"
            );
            if (!accepted) {
                event.preventDefault();
            }
        });
    }
});
