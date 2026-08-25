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
        booking_external_block_deleted: "Bloqueo eliminado.",
        booking_guest_updated: "Huésped actualizado.",
        platform_created: "Plataforma creada.",
        platform_updated: "Plataforma actualizada.",
        platform_deleted: "Plataforma eliminada.",
        room_calendar_created: "Calendario configurado.",
        room_calendar_updated: "Configuración guardada.",
        room_calendar_toggled: "Estado del calendario actualizado.",
        room_calendar_deleted: "Calendario eliminado.",
        room_calendar_sync_completed: "Calendario sincronizado correctamente.",
        room_calendar_sync_completed_with_warnings: "Calendario sincronizado con advertencias; las reservas canceladas o desaparecidas se han conservado.",
        room_calendar_automatic_enabled: "Sincronización automática activada.",
        room_calendar_automatic_paused: "Sincronización automática pausada.",
        master_calendar_token_regenerated: "URL del calendario maestro regenerada. Actualiza esta URL en todas las plataformas."
        ,photos_uploaded: "Fotografías subidas correctamente."
        ,photo_primary_updated: "Foto principal actualizada."
        ,photos_reordered: "Orden de fotografías actualizado."
        ,photo_deleted: "Fotografía eliminada."
        ,publication_saved: "Publicación guardada."
        ,feature_saved: "Característica guardada."
        ,feature_deleted: "Característica eliminada."
        ,room_configuration_copied: "Configuración copiada."
        ,property_rules_saved: "Normas y requisitos guardados."
        ,requirement_saved: "Requisito guardado."
        ,requirement_deleted: "Requisito eliminado."
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
        booking_not_imported: "Esta acción solo está disponible para reservas importadas.",
        booking_external_block_still_present: "El bloqueo sigue presente en la plataforma externa. Elimínalo primero allí.",
        booking_external_block_presence_unknown: "Todavía no se ha podido confirmar que el bloqueo haya desaparecido de la plataforma.",
        booking_room_not_found: "La habitación asociada a la reserva no existe.",
        room_calendar_exists: "Esta plataforma ya está configurada para la habitación.",
        room_calendar_room_inactive: "No se puede crear o reactivar un calendario en una habitación inactiva.",
        room_calendar_platform_inactive: "No se puede crear o reactivar un calendario de una plataforma inactiva.",
        room_calendar_import_url_required: "Debe indicar la URL externa de importación.",
        room_calendar_import_not_supported: "La plataforma no admite URL de importación.",
        room_calendar_export_not_supported: "La plataforma no admite URL de exportación.",
        room_calendar_invalid_url: "Las URLs deben ser direcciones http o https válidas.",
        room_calendar_has_bookings: "No se puede eliminar un calendario con reservas históricas.",
        room_calendar_inactive: "El calendario está inactivo.",
        room_calendar_sync_overlap: "La sincronización se solapa con otra reserva y no se ha aplicado.",
        room_calendar_sync_unsafe_url: "La URL del calendario apunta a un destino de red no permitido.",
        room_calendar_sync_download_failed: "No se pudo descargar el calendario.",
        room_calendar_sync_failed: "La sincronización no pudo aplicarse y no se guardó ningún cambio.",
        room_calendar_sync_timeout: "La descarga del calendario agotó el tiempo disponible.",
        room_calendar_sync_too_large: "El calendario supera el tamaño máximo permitido.",
        room_calendar_sync_too_many_redirects: "El calendario contiene demasiadas redirecciones.",
        room_calendar_sync_too_many_events: "El calendario supera el número máximo de eventos.",
        room_calendar_sync_recurrence_not_supported: "Los eventos recurrentes todavía no están admitidos.",
        room_calendar_sync_incompatible_stay: "El calendario contiene una estancia de una sola jornada, incompatible con RentalManager.",
        room_calendar_sync_invalid_feed: "El contenido recibido no es un calendario iCal válido.",
        room_calendar_sync_in_progress: "Este calendario ya se está sincronizando.",
        room_calendar_sync_rate_limited: "La plataforma ha limitado temporalmente las consultas.",
        room_calendar_sync_http_server_error: "La plataforma tiene un error temporal.",
        room_calendar_sync_http_access_error: "La plataforma rechazó el acceso a la URL configurada.",
        room_calendar_sync_http_error: "La plataforma rechazó la solicitud del calendario.",
        room_calendar_sync_database_locked: "La base de datos está ocupada; inténtalo más tarde.",
        room_calendar_sync_database_error: "Se produjo un error de base de datos.",
        room_calendar_sync_unexpected_error: "Se produjo un error inesperado durante la sincronización.",
        room_calendar_automatic_unavailable: "La sincronización automática no está disponible para esta configuración."
        ,media_file_required: "Selecciona al menos una imagen."
        ,media_file_too_large: "La imagen supera el máximo de 10 MiB."
        ,media_too_many_pixels: "La imagen supera el límite de 40 millones de píxeles."
        ,media_unsupported_format: "Solo se admiten imágenes JPEG, PNG o WebP no animadas."
        ,media_animated_not_allowed: "No se admiten imágenes animadas."
        ,media_mime_mismatch: "El contenido de la imagen no coincide con el tipo declarado."
        ,media_invalid_image: "El archivo no contiene una imagen válida."
        ,media_duplicate_photo: "Esta fotografía ya está asociada al registro."
        ,public_slug_invalid: "El slug debe contener solo minúsculas, números y guiones."
        ,public_slug_exists: "Ese slug público ya está en uso."
        ,publication_requirements: "No se puede publicar porque faltan requisitos. Revisa el estado de publicabilidad."
        ,feature_invalid: "Los datos de la característica no son válidos."
        ,feature_slug_exists: "Ese slug de característica ya existe."
        ,feature_in_use: "No se puede eliminar una característica que está asignada. Desactívala."
        ,feature_inactive: "No se puede añadir una característica inactiva."
        ,feature_wrong_scope: "La característica no corresponde a este tipo de registro."
        ,room_commercial_values_invalid: "El precio y la superficie deben ser números válidos mayores o iguales que cero."
        ,room_stay_conditions_invalid: "Las condiciones de estancia deben expresarse en meses válidos."
        ,room_stay_range_invalid: "La estancia máxima no puede ser menor que la mínima."
        ,room_feature_copy_same_room: "Selecciona una habitación de origen diferente."
        ,property_rules_invalid: "Los valores de normas no son válidos."
        ,property_age_invalid: "Las edades deben ser números no negativos."
        ,property_age_range_invalid: "La edad máxima no puede ser menor que la mínima."
        ,property_shared_bathroom_counts_invalid: "Los contadores de baños y aseos deben ser enteros mayores o iguales que cero."
        ,requirement_invalid: "Los datos del requisito no son válidos."
        ,requirement_slug_exists: "Ese slug de requisito ya existe."
        ,requirement_inactive: "No se puede asignar un requisito inactivo."
        ,requirement_in_use: "No se puede eliminar un requisito asignado. Desactívalo."
    },

    show() {
        const params = new URLSearchParams(window.location.search);
        const success = params.get("success");
        const error = params.get("error");
        let shown = false;

        if (success && this.successMessages[success]) {
            let message = this.successMessages[success];
            if (success === "room_configuration_copied") {
                const source = params.get("source");
                const omitted = Number(params.get("omitted") || 0);
                message = omitted > 0
                    ? `Configuración copiada. ${omitted} elemento${omitted === 1 ? "" : "s"} no aplicable${omitted === 1 ? "" : "s"} fue${omitted === 1 ? "" : "ron"} omitido${omitted === 1 ? "" : "s"}.`
                    : `Configuración copiada desde ${source || "la habitación seleccionada"}.`;
            }
            RMNotification.success(message);
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
        params.delete("source");
        params.delete("omitted");

        const query = params.toString();
        const url = `${window.location.pathname}${query ? `?${query}` : ""}${window.location.hash}`;
        history.replaceState({}, "", url);
    }

};

document.addEventListener("DOMContentLoaded", () => {
    RMPageNotification.show();
});
