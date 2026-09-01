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
        this.financeButton = document.getElementById("bookingFinanceButton");

        this.importedNotice = document.getElementById("bookingImportedNotice");

        this.roomId = document.getElementById("bookingRoomId");

        this.guestName = document.getElementById("bookingGuestName");
        this.guestNameGroup = document.getElementById("bookingGuestNameGroup");
        this.guestNameLabel = document.getElementById("bookingGuestNameLabel");
        this.guestNameHelp = document.getElementById("bookingGuestNameHelp");
        this.partiesSection = document.getElementById("bookingPartiesSection");
        this.partiesList = document.getElementById("bookingPartiesList");
        this.partyPerson = document.getElementById("bookingPartyPerson");
        this.partyRole = document.getElementById("bookingPartyRole");
        this.partyAdd = document.getElementById("bookingPartyAdd");

        this.checkIn = document.getElementById("bookingCheckIn");

        this.checkOut = document.getElementById("bookingCheckOut");

        this.expectedArrivalDate = document.getElementById("bookingExpectedArrivalDate");

        this.expectedDepartureDate = document.getElementById("bookingExpectedDepartureDate");

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

        this.partyAdd?.addEventListener("click", () => this.addParty());

    },

    openCreateModal(roomId = null, checkIn = null) {

        this.resetModalState();

        this.clearForm();

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

            this.resetModalState();

            this.bookingId = booking.id;
            this.financeButton.href = `/bookings/${booking.id}/finance`;
            this.financeButton.classList.remove("d-none");

            this.fillForm(booking);
            await this.loadPersonOptions();
            this.renderParties(booking.parties || []);
            this.partiesSection.classList.remove("d-none");

            const imported = readOnly || booking.editable === false;

            this.form.action = imported
                ? `/bookings/update-imported-local/${booking.id}`
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

        const creating = this.form.action.endsWith("/bookings/create");

        this.guestNameGroup.classList.toggle("d-none", !creating && !readOnly);
        this.guestName.disabled = !creating && !readOnly;
        this.guestName.readOnly = readOnly;

        this.roomId.disabled = false;

        this.guestName.required = creating;

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
        this.guestNameLabel.textContent = readOnly ? "Nombre recibido de la plataforma" : "Inquilino inicial";
        this.guestNameHelp.textContent = readOnly
            ? "Este texto procede de la plataforma y no puede modificarse aquí."
            : "Se creará una persona sin clasificar. Después podrás asignar sus roles.";

        this.title.textContent = readOnly
            ? "Detalle de reserva importada"
            : (this.form.action === "/bookings/create" ? "Nueva reserva" : "Editar reserva");

        this.submitButton.textContent = readOnly ? "Guardar datos locales" :
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

        this.roomId.value = booking.room_id;

        this.guestName.value = booking.source_guest_name ?? "";

        this.checkIn.value = booking.check_in;

        this.checkOut.value = booking.check_out;

        this.expectedArrivalDate.value = booking.expected_arrival_date ?? "";

        this.expectedDepartureDate.value = booking.expected_departure_date ?? "";

        this.price.value = booking.price ?? "";

        this.notes.value = booking.notes ?? "";

    },

    clearForm() {

        this.form.reset();

    },

    roleLabel(role) {
        return {tenant: "Arrendatario", occupant: "Ocupante", payer: "Responsable de pago", guarantor: "Avalista", unclassified: "Sin clasificar"}[role] || role;
    },

    async loadPersonOptions() {
        const response = await fetch("/persons/options");
        if (!response.ok) throw new Error("No se han podido cargar las personas.");
        const persons = await response.json();
        this.partyPerson.innerHTML = '<option value="">Selecciona una persona</option>';
        persons.forEach(person => {
            const option = document.createElement("option");
            option.value = person.id;
            option.textContent = person.name;
            this.partyPerson.append(option);
        });
    },

    renderParties(parties) {
        this.currentParties = parties;
        this.partiesList.innerHTML = "";
        if (!parties.length) {
            this.partiesList.innerHTML = '<p class="text-muted small mb-0">No hay personas vinculadas.</p>';
            return;
        }
        const groups = ["tenant", "occupant", "payer", "guarantor", "unclassified"];
        groups.forEach(group => {
          const groupedParties = parties.filter(party => party.role === group);
          if (!groupedParties.length) return;
          const heading = document.createElement("h6");
          heading.className = "small text-muted mt-2 mb-1";
          heading.textContent = this.roleLabel(group);
          this.partiesList.append(heading);
          groupedParties.forEach(party => {
            const row = document.createElement("div");
            row.className = "d-flex justify-content-between align-items-center gap-2 border rounded p-2 mb-2";
            const copy = document.createElement("div");
            const link = document.createElement("a"); link.href = `/persons/${party.person_id}`; link.textContent = party.person_name; link.target = "_blank"; link.rel = "noopener";
            copy.append(link);
            const remove = document.createElement("button"); remove.type = "button"; remove.className = "btn btn-sm btn-outline-danger"; remove.textContent = "Retirar rol"; remove.addEventListener("click", () => this.removeParty(party.id));
            row.append(copy, remove); this.partiesList.append(row);
          });
        });
    },

    async addParty() {
        if (!this.bookingId || !this.partyPerson.value) return;
        const body = new FormData(); body.set("person_id", this.partyPerson.value); body.set("role", this.partyRole.value);
        const response = await fetch(`/bookings/${this.bookingId}/parties`, {method: "POST", body});
        if (!response.ok) { RMNotification.error("No se ha podido vincular la persona o el rol ya existe."); return; }
        const party = await response.json(); this.renderParties([...this.currentParties, party]);
    },

    async removeParty(partyId) {
        const response = await fetch(`/bookings/${this.bookingId}/parties/${partyId}/remove`, {method: "POST"});
        if (!response.ok) { RMNotification.error("No se ha podido retirar el rol."); return; }
        this.renderParties(this.currentParties.filter(party => party.id !== partyId));
    },

    resetModalState() {

        this.bookingId = null;

        this.importedGuestMode = false;

        this.externalBlockDeletable = false;

        this.form.action = "/bookings/create";

        this.roomId.disabled = false;

        this.guestName.disabled = false;
        this.guestName.readOnly = false;
        this.guestNameGroup.classList.remove("d-none");

        this.guestName.required = true;

        [this.checkIn, this.checkOut, this.price, this.notes]
            .forEach(field => field.disabled = false);

        [this.expectedArrivalDate, this.expectedDepartureDate]
            .forEach(field => field.disabled = false);

        this.title.textContent = "Nueva reserva";
        this.guestNameLabel.textContent = "Inquilino inicial";
        this.guestNameHelp.textContent = "En una reserva nueva se creará una persona sin clasificar. Después podrás asignar sus roles.";

        this.submitButton.textContent = "Guardar";

        this.submitButton.classList.remove("d-none");

        this.deleteButton.classList.add("d-none");
        this.financeButton.classList.add("d-none");
        this.financeButton.href = "#";

        this.deleteButton.textContent = "Eliminar";

        this.importedNotice.classList.add("d-none");
        this.partiesSection.classList.add("d-none");
        this.partiesList.innerHTML = "";
        this.currentParties = [];

    },

    validateForm() {

        const validator = new RMValidator();

        if (this.form.action.endsWith("/bookings/create")) {
            validator.addRule(
                this.guestName,
                value => value.trim() !== "",
                "Debe introducir el nombre del inquilino inicial."
            );
        }

        validator.addRule(

            this.checkOut,

            () => this.checkOut.value > this.checkIn.value,

            "El fin de contrato debe ser posterior al inicio de contrato."

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
