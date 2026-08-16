const RMPageNotification = {

    successMessages: {
        property_created: "Propiedad creada.",
        property_updated: "Propiedad actualizada.",
        property_deleted: "Propiedad eliminada.",
        room_created: "Habitación creada.",
        room_updated: "Habitación actualizada.",
        room_deleted: "Habitación eliminada.",
        booking_created: "Reserva creada.",
        booking_updated: "Reserva actualizada.",
        booking_deleted: "Reserva eliminada.",
        platform_created: "Plataforma creada.",
        platform_updated: "Plataforma actualizada.",
        platform_deleted: "Plataforma eliminada.",
        room_calendar_created: "Calendario configurado.",
        room_calendar_updated: "Configuración de calendario actualizada.",
        room_calendar_toggled: "Estado del calendario actualizado.",
        room_calendar_deleted: "Calendario eliminado."
    },

    errorMessages: {
        name_exists: "Ya existe una propiedad con ese nombre.",
        property_has_rooms: "No se puede eliminar una propiedad que contiene habitaciones.",
        code_exists: "Ya existe una habitación con ese código.",
        room_has_bookings: "No se puede eliminar una habitación con reservas.",
        room_has_room_calendars: "No se puede eliminar una habitación con calendarios configurados.",
        slug_exists: "Ya existe una plataforma con ese slug.",
        not_found: "El registro solicitado no existe.",
        platform_has_room_calendars: "No se puede eliminar una plataforma con calendarios configurados.",
        platform_capabilities_in_use: "No se pueden retirar capacidades utilizadas por calendarios configurados.",
        booking_overlap: "Las fechas se solapan con otra reserva de la habitación.",
        booking_room_inactive: "No se pueden guardar reservas en una habitación inactiva.",
        booking_guest_required: "Debe introducir el nombre del huésped.",
        booking_invalid_dates: "La fecha de salida debe ser posterior a la fecha de entrada.",
        booking_invalid_price: "El precio mensual debe ser un número mayor o igual que cero.",
        booking_imported_read_only: "Las reservas importadas no se pueden modificar manualmente.",
        booking_room_not_found: "La habitación asociada a la reserva no existe.",
        booking_delete_not_allowed: "Las reservas no se pueden eliminar para preservar el histórico.",
        room_calendar_exists: "Esta plataforma ya está configurada para la habitación.",
        room_calendar_room_inactive: "No se puede crear o reactivar un calendario en una habitación inactiva.",
        room_calendar_platform_inactive: "No se puede crear o reactivar un calendario de una plataforma inactiva.",
        room_calendar_url_required: "Debe indicar al menos una URL compatible.",
        room_calendar_import_not_supported: "La plataforma no admite URL de importación.",
        room_calendar_export_not_supported: "La plataforma no admite URL de exportación.",
        room_calendar_invalid_url: "Las URLs deben ser direcciones http o https válidas.",
        room_calendar_has_bookings: "No se puede eliminar un calendario con reservas históricas."
    },

    show() {
        const params = new URLSearchParams(window.location.search);
        const success = params.get("success");
        const error = params.get("error");
        let shown = false;

        if (success && this.successMessages[success]) {
            RMNotification.success(this.successMessages[success]);
            shown = true;
        }

        if (error && this.errorMessages[error]) {
            RMNotification.error(this.errorMessages[error]);
            shown = true;
        }

        if (!shown) {
            return;
        }

        params.delete("success");
        params.delete("error");

        const query = params.toString();
        const url = `${window.location.pathname}${query ? `?${query}` : ""}${window.location.hash}`;
        history.replaceState({}, "", url);
    }

};

document.addEventListener("DOMContentLoaded", () => {
    RMPageNotification.show();
});
