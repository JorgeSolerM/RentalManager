function openCreateRoomModal(propertyId) {

    document.getElementById("room-modal-title").textContent =
        "Nueva habitación";

    document.getElementById("room-modal-submit").textContent =
        "Guardar";

    document.getElementById("room-form").action =
        "/rooms/create";

    document.getElementById("property_id").value =
        propertyId;

    clearRoomForm();

    document
        .getElementById("room-modal")
        .classList.remove("hidden");

}


function closeRoomModal() {

    document
        .getElementById("room-modal")
        .classList.add("hidden");

}


function clearRoomForm() {

    document
        .getElementById("room-form")
        .reset();

}
