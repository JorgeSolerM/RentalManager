const BookingUI = {

    init() {

        this.cacheDom();

        this.bindEvents();

    },

    cacheDom() {

        this.modalElement = document.getElementById("bookingModal");

        this.modal = new bootstrap.Modal(this.modalElement);

        this.form = document.getElementById("bookingForm");

        this.title = document.getElementById("bookingModalTitle");

        this.submitButton = document.getElementById("bookingSubmitButton");

        this.deleteButton = document.getElementById("bookingDeleteButton");

        this.roomId = document.getElementById("bookingRoomId");

        this.guestName = document.getElementById("bookingGuestName");

        this.checkIn = document.getElementById("bookingCheckIn");

        this.checkOut = document.getElementById("bookingCheckOut");

        this.price = document.getElementById("bookingPrice");

        this.notes = document.getElementById("bookingNotes");

        this.newBookingButton = document.querySelector(
            "[data-bs-target='#bookingModal']"
        );

    },

    bindEvents() {

        this.newBookingButton.addEventListener("click", () => {

            this.openCreateModal();

        });

        document.querySelectorAll(".booking-link").forEach((link) => {

            link.addEventListener("click", (event) => {

                event.preventDefault();

                const bookingId = link.dataset.bookingId;

                this.openEditModal(bookingId);

            });

        });

        this.form.addEventListener("submit", (event) => {

            if (!this.validateForm()) {

                event.preventDefault();

            }

        });

        this.deleteButton.addEventListener("click", () => {

            this.handleDelete();

        });

    },

    openCreateModal() {

        this.clearForm();

        this.title.textContent = "Nueva reserva";

        this.form.action = "/bookings/create";

        this.submitButton.textContent = "Guardar";

        this.deleteButton.classList.add("d-none");

    },

    async openEditModal(bookingId) {

        try {

            const response = await fetch(`/bookings/${bookingId}`);

            if (!response.ok) {

                throw new Error("No se ha podido cargar la reserva.");

            }

            const booking = await response.json();

            this.fillForm(booking);

            this.title.textContent = "Editar reserva";

            this.form.action = `/bookings/update/${booking.id}`;

            this.submitButton.textContent = "Guardar cambios";

            this.deleteButton.classList.remove("d-none");

            this.modal.show();

        } catch (error) {

            console.error(error);

            RMNotification.error(
                "No se ha podido cargar la reserva."
            );

        }

    },

    handleDelete() {

        if (!RMConfirm.ask(
            "¿Desea eliminar esta reserva?"
        )) {

            return;

        }

        this.form.action = this.form.action.replace(
            "/update/",
            "/delete/"
        );

        this.form.submit();

    },

    fillForm(booking) {

        this.guestName.value = booking.guest_name;

        this.checkIn.value = booking.check_in;

        this.checkOut.value = booking.check_out;

        this.price.value = booking.price ?? "";

        this.notes.value = booking.notes ?? "";

    },

    clearForm() {

        this.form.reset();

    },

    validateForm() {

        const validator = new RMValidator();

        validator.addRule(

            this.guestName,

            value => value.trim() !== "",

            "Debe introducir el nombre del huésped."

        );

        validator.addRule(

            this.checkOut,

            () => this.checkOut.value > this.checkIn.value,

            "La fecha de salida debe ser posterior a la fecha de entrada."

        );

        validator.addRule(

            this.price,

            value => value === "" || Number(value) >= 0,

            "El precio no puede ser negativo."

        );

        return validator.validate();

    },

    validateGuestName() {

        if (this.guestName.value.trim() === "") {

            RMNotification.error(
                "Debe introducir el nombre del huésped."
            );

            this.guestName.focus();

            return false;

        }

        return true;

    },

    validateDates() {

        if (this.checkOut.value <= this.checkIn.value) {

            RMNotification.error(
                "La fecha de salida debe ser posterior a la fecha de entrada."
            );

            this.checkOut.focus();

            return false;

        }

        return true;

    },

    validatePrice() {

        if (

            this.price.value !== ""

            && Number(this.price.value) < 0

        ) {

            RMNotification.error(
                "El precio no puede ser negativo."
            );

            this.price.focus();

            return false;

        }

        return true;

    }

};

const BOOKING_ERROR_MESSAGES = {

    booking_overlap:
        "Las fechas se solapan con otra reserva de la habitación.",

    booking_room_inactive:
        "No se pueden guardar reservas en una habitación inactiva.",

    booking_guest_required:
        "Debe introducir el nombre del huésped.",

    booking_invalid_dates:
        "La fecha de salida debe ser posterior a la fecha de entrada.",

    booking_invalid_price:
        "El precio mensual debe ser un número mayor o igual que cero.",

    booking_imported_read_only:
        "Las reservas importadas no se pueden modificar manualmente.",

    booking_room_not_found:
        "La habitación asociada a la reserva no existe.",

    room_calendar_exists:
        "Esta plataforma ya está configurada para la habitación.",

    room_calendar_room_inactive:
        "No se puede crear o reactivar un calendario en una habitación inactiva.",

    room_calendar_platform_inactive:
        "No se puede crear o reactivar un calendario de una plataforma inactiva.",

    room_calendar_url_required:
        "Debe indicar al menos una URL compatible.",

    room_calendar_import_not_supported:
        "La plataforma no admite URL de importación.",

    room_calendar_export_not_supported:
        "La plataforma no admite URL de exportación.",

    room_calendar_invalid_url:
        "Las URLs deben ser direcciones http o https válidas.",

    room_calendar_has_bookings:
        "No se puede eliminar un calendario con reservas históricas.",

    booking_delete_not_allowed:
        "Las reservas no se pueden eliminar para preservar el histórico."

};

const ROOM_WORKSPACE_SUCCESS_MESSAGES = {

    room_calendar_created:
        "Calendario configurado.",

    room_calendar_updated:
        "Configuración de calendario actualizada.",

    room_calendar_toggled:
        "Estado del calendario actualizado.",

    room_calendar_deleted:
        "Calendario eliminado."

};

document.addEventListener("DOMContentLoaded", () => {

    RMPageNotification.show(
        ROOM_WORKSPACE_SUCCESS_MESSAGES,
        BOOKING_ERROR_MESSAGES,
    );

    if (!document.getElementById("bookingModal")) {

        return;

    }

    BookingUI.init();

});
