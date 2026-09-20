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
        this.sepaButton = document.getElementById("bookingSepaButton");

        this.importedNotice = document.getElementById("bookingImportedNotice");

        this.roomId = document.getElementById("bookingRoomId");

        this.guestName = document.getElementById("bookingGuestName");
        this.guestNameGroup = document.getElementById("bookingGuestNameGroup");
        this.guestNameLabel = document.getElementById("bookingGuestNameLabel");
        this.guestNameHelp = document.getElementById("bookingGuestNameHelp");
        this.partiesSection = document.getElementById("bookingPartiesSection");
        this.partiesList = document.getElementById("bookingPartiesList");
        this.partyPerson = document.getElementById("bookingPartyPerson");
        this.initialFunctions = document.getElementById("bookingInitialFunctions");
        this.partyFunctions = document.getElementById("bookingPartyFunctions");
        this.partyWarning = document.getElementById("bookingPartyWarning");
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
            this.sepaButton.href = `/sepa/bookings/${booking.id}`;
            this.sepaButton.classList.remove("d-none");

            this.fillForm(booking);
            await this.loadPersonOptions();
            await this.reloadParties();
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
        this.initialFunctions.classList.toggle('d-none', !creating);
        this.initialFunctions.disabled = !creating;

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
            : "Una persona con las funciones que selecciones para esta reserva.";

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
        const people = new Map();
        parties.forEach(party => {
            if (!people.has(party.person_id)) people.set(party.person_id, { ...party, roles: [] });
            people.get(party.person_id).roles.push(party.role);
        });
        people.forEach(party => {
            const order = ['tenant', 'payer', 'occupant', 'guarantor', 'unclassified'];
            party.roles.sort((a, b) => order.indexOf(a) - order.indexOf(b));
            const row = document.createElement("div");
            row.className = "border rounded p-2 mb-2";
            row.dataset.personId = party.person_id;
            const copy = document.createElement("div");
            const link = document.createElement("a"); link.className = 'text-break'; link.href = `/persons/${party.person_id}`; link.textContent = party.person_name; link.target = "_blank"; link.rel = "noopener";
            copy.append(link);
            const edit = document.createElement('button'); edit.type = 'button'; edit.className = 'btn btn-link btn-sm'; edit.textContent = '✎'; edit.title = 'Editar funciones'; edit.setAttribute('aria-label', `Editar funciones de ${party.person_name}`);
            edit.addEventListener('click', () => this.editFunctions(row, party, edit)); copy.append(edit);
            const badges = document.createElement('div'); badges.className = 'd-flex flex-wrap gap-1 my-1';
            party.roles.forEach(role => { const badge = document.createElement('span'); badge.className = 'badge text-bg-light'; badge.textContent = this.roleLabel(role); badges.append(badge); });
            const remove = document.createElement("button"); remove.type = "button"; remove.className = "btn btn-sm btn-link text-danger px-0"; remove.textContent = "Desvincular persona";
            remove.addEventListener('click', () => {
                if (RMConfirm.ask('¿Desvincular esta persona y todas sus funciones de la reserva? No se elimina su ficha.')) this.mutatePerson(party.person_id, 'remove', [], remove);
            });
            row.append(copy, badges, remove); this.partiesList.append(row);
        });
    },

    async reloadParties() {
        const response = await fetch(`/bookings/${this.bookingId}/people`);
        if (!response.ok) throw new Error('No se pudieron cargar las funciones.');
        this.showParties(await response.json());
    },

    showParties(data) {
        this.renderParties(data.parties);
        this.partyWarning.textContent = data.warning || '';
        this.partyWarning.classList.toggle('d-none', !data.warning);
    },

    editFunctions(row, party, trigger) {
        if (row.querySelector('fieldset')) return;
        trigger.disabled = true;
        const editor = document.createElement('fieldset'); editor.className = 'mt-2';
        const legend = document.createElement('legend'); legend.className = 'fs-6'; legend.textContent = 'Funciones en la reserva'; editor.append(legend);
        const roles = ['tenant', 'payer', 'occupant', 'guarantor'];
        if (party.roles.includes('unclassified')) roles.push('unclassified');
        roles.forEach(role => {
            const label = document.createElement('label'); label.className = 'd-block py-1';
            const input = document.createElement('input'); input.type = 'checkbox'; input.value = role; input.checked = party.roles.includes(role); input.className = 'form-check-input me-2';
            input.addEventListener('change', () => {
                if (input.checked) editor.querySelectorAll('input').forEach(other => { if (other !== input && (role === 'unclassified' || other.value === 'unclassified')) other.checked = false; });
            });
            label.append(input, document.createTextNode(this.roleLabel(role))); editor.append(label);
        });
        const save = document.createElement('button'); save.type = 'button'; save.className = 'btn btn-primary btn-sm me-2'; save.textContent = 'Guardar funciones';
        save.addEventListener('click', () => this.mutatePerson(party.person_id, 'roles', [...editor.querySelectorAll('input:checked')].map(i => i.value), save));
        const cancel = document.createElement('button'); cancel.type = 'button'; cancel.className = 'btn btn-outline-secondary btn-sm'; cancel.textContent = 'Cancelar';
        const close = () => { editor.remove(); trigger.disabled = false; trigger.focus(); };
        cancel.addEventListener('click', close);
        editor.addEventListener('keydown', event => {
            if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); close(); }
            if (event.key === 'Enter' && event.target.tagName === 'INPUT') { event.preventDefault(); save.click(); }
        });
        editor.append(save, cancel); row.append(editor); editor.querySelector('input').focus();
    },

    async addParty() {
        if (!this.bookingId || !this.partyPerson.value) return;
        await this.mutatePerson(this.partyPerson.value, 'add', [...this.partyFunctions.querySelectorAll('input:checked')].map(i => i.value), this.partyAdd);
    },

    async mutatePerson(personId, action, roles, button) {
        if (action !== 'remove' && !roles.length) { RMNotification.error('Selecciona al menos una función para el inquilino.'); return; }
        const body = new FormData(); body.set('person_id', personId); roles.forEach(role => body.append('roles', role));
        const url = `/bookings/${this.bookingId}/people` + (action === 'add' ? '' : `/${personId}/${action}`);
        button.disabled = true;
        try {
            let response = await fetch(url, {method:'POST',body});
            let data = await response.json();
            if (response.status === 409) {
                if (!RMConfirm.ask(data.detail)) return;
                body.set('confirm_sepa_review','true'); response = await fetch(url,{method:'POST',body}); data = await response.json();
            }
            if (!response.ok) { RMNotification.error(typeof data.detail === 'string' ? data.detail : 'No se pudieron guardar las funciones.'); return; }
            this.showParties(data); this.partyPerson.focus();
        } catch (error) { RMNotification.error('No se pudieron guardar las funciones. Revisa la conexión e inténtalo de nuevo.'); }
        finally { button.disabled = false; }
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
        this.guestNameHelp.textContent = "Una persona con las funciones que selecciones para esta reserva.";
        this.initialFunctions.disabled = false;
        this.initialFunctions.classList.remove('d-none');
        this.partyFunctions.querySelectorAll('input').forEach(input => input.checked = false);
        this.partyWarning.classList.add('d-none');

        this.submitButton.textContent = "Guardar";

        this.submitButton.classList.remove("d-none");

        this.deleteButton.classList.add("d-none");
        this.financeButton.classList.add("d-none");
        this.financeButton.href = "#";
        this.sepaButton.classList.add("d-none");
        this.sepaButton.href = "#";

        this.deleteButton.textContent = "Eliminar";

        this.importedNotice.classList.add("d-none");
        this.partiesSection.classList.add("d-none");
        this.partiesList.innerHTML = "";
        this.currentParties = [];

    },

    validateForm() {

        const validator = new RMValidator();

        if (this.form.action.endsWith("/bookings/create")) {
            if (!this.initialFunctions.querySelector('input[type=checkbox]:checked')) {
                RMNotification.error('Selecciona al menos una función para el inquilino.');
                this.initialFunctions.querySelector('input[type=checkbox]').focus();
                return false;
            }
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
