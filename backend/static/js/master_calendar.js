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
                "Las URLs actuales dejarán de funcionar inmediatamente. Será necesario sustituirlas en HousingAnywhere, Flatio, Spotahome y cualquier otra plataforma donde estén configuradas. No es necesario hacer esto cuando cambian las reservas: el contenido del calendario se actualiza manteniendo las mismas URLs. ¿Continuar?"
            );
            if (!accepted) {
                event.preventDefault();
            }
        });
    }
});
