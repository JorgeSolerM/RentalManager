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

        this.importedNotice = document.getElementById("bookingImportedNotice");

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

        this.newBookingButton?.addEventListener("click", () => {

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

            if (!this.importedGuestMode && !this.validateForm()) {

                event.preventDefault();

            }

        });

        this.deleteButton.addEventListener("click", () => {

            this.handleDelete();

        });

    },

    openCreateModal(roomId = null, checkIn = null) {

        this.clearForm();

        this.title.textContent = "Nueva reserva";

        this.form.action = "/bookings/create";

        this.submitButton.textContent = "Guardar";

        this.deleteButton.classList.add("d-none");

        this.setReadOnly(false);

        if (roomId !== null) this.roomId.value = roomId;

        if (checkIn !== null) this.checkIn.value = checkIn;

    },

    async openEditModal(bookingId, readOnly = false) {

        try {

            const response = await fetch(`/bookings/${bookingId}`);

            if (!response.ok) {

                throw new Error("No se ha podido cargar la reserva.");

            }

            const booking = await response.json();

            this.bookingId = booking.id;

            this.fillForm(booking);

            const imported = readOnly || booking.editable === false;

            this.form.action = imported
                ? `/bookings/update-imported-guest/${booking.id}`
                : `/bookings/update/${booking.id}`;

            this.setReadOnly(imported, booking.external_block_deletable === true);

            this.modal.show();

        } catch (error) {

            console.error(error);

            RMNotification.error(
                "No se ha podido cargar la reserva."
            );

        }

    },

    setReadOnly(readOnly, externalBlockDeletable = false) {

        this.importedGuestMode = readOnly;

        this.guestName.disabled = false;

        this.guestName.required = !readOnly;

        [this.checkIn, this.checkOut, this.price, this.notes]
            .forEach(field => field.disabled = readOnly);

        this.submitButton.classList.remove("d-none");

        this.deleteButton.classList.toggle(
            "d-none",
            (readOnly && !externalBlockDeletable) || this.form.action === "/bookings/create"
        );

        this.deleteButton.textContent = externalBlockDeletable
            ? "Eliminar bloqueo"
            : "Eliminar";

        this.externalBlockDeletable = externalBlockDeletable;

        this.importedNotice.classList.toggle("d-none", !readOnly);

        this.title.textContent = readOnly
            ? "Detalle de reserva importada"
            : (this.form.action === "/bookings/create" ? "Nueva reserva" : "Editar reserva");

        this.submitButton.textContent = readOnly ? "Guardar huésped" :
            (this.form.action === "/bookings/create" ? "Guardar" : "Guardar cambios");

    },

    handleDelete() {

        const confirmation = this.externalBlockDeletable
            ? "¿Desea eliminar este bloqueo desaparecido? Esta acción no se puede deshacer."
            : "¿Desea eliminar esta reserva manual? Esta acción no se puede deshacer.";

        if (!RMConfirm.ask(confirmation)) {

            return;

        }

        this.form.action = `/bookings/delete/${this.bookingId}`;

        this.form.submit();

    },

    fillForm(booking) {

        this.guestName.value = booking.guest_name ?? "";

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

document.addEventListener("DOMContentLoaded", () => {
    if (!document.getElementById("bookingModal")) {

        return;

    }

    BookingUI.init();

});
