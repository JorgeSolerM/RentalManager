document.addEventListener("DOMContentLoaded", () => {
    const form = document.querySelector("[data-copy-room-configuration]");
    if (!form) return;

    form.addEventListener("submit", (event) => {
        const select = form.querySelector("select[name='source_room_id']");
        if (!select.value) return;
        const source = select.options[select.selectedIndex].textContent.trim();
        const destination = form.dataset.destinationCode;
        const confirmed = window.confirm(
            `Se sustituirán el título, la descripción, las características, los destacados y las condiciones de estancia actuales de ${destination} por la configuración de ${source}. ` +
            "No se modificarán fotos, precio, superficie, slug, gestor ni datos del inmueble."
        );
        if (!confirmed) event.preventDefault();
    });
});
