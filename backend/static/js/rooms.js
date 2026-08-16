document.addEventListener("DOMContentLoaded", () => {
    const roomDeleteButton = document.getElementById(
        "room-modal-delete"
    );

    if (roomDeleteButton) {

        roomDeleteButton.addEventListener(
            "click",
            handleDeleteRoom,
        );

    }

});


function openCreateRoomModal(propertyId) {

    document.getElementById("room-modal-title").textContent =
        "Nueva habitación";

    document.getElementById("room-modal-submit").textContent =
        "Guardar";

    document.getElementById("room-form").action =
        "/rooms/create";

    document
        .getElementById("room-modal-delete")
        .classList.add("hidden");

    document.getElementById("property_id").value =
        propertyId;

    clearRoomForm();

    document
        .getElementById("room-modal")
        .classList.remove("hidden");

}


async function openEditRoomModal(roomId) {

    try {

        const response = await fetch(
            `/rooms/edit/${roomId}`
        );

        if (!response.ok) {

            throw new Error(
                "No se ha podido cargar la habitación."
            );

        }

        const room = await response.json();

        document.getElementById("room-modal-title").textContent =
            "Editar habitación";

        document.getElementById("room-modal-submit").textContent =
            "Guardar cambios";

        document.getElementById("room-form").action =
            `/rooms/update/${room.id}`;

        document.getElementById("property_id").value =
            room.property_id;

        document.getElementById("code").value =
            room.code;

        document.getElementById("base_price").value =
            room.base_price;

        document.getElementById("square_meters").value =
            room.square_meters ?? "";

        document
            .getElementById("room-modal-delete")
            .classList.remove("hidden");

        document
            .getElementById("room-modal")
            .classList.remove("hidden");

    }

    catch (error) {

        console.error(error);

        RMNotification.error(
            "No se ha podido cargar la habitación."
        );

    }

}


function handleDeleteRoom() {

    if (!RMConfirm.ask(
        "¿Desea eliminar esta habitación?"
    )) {

        return;

    }

    const form = document.getElementById(
        "room-form"
    );

    form.action = form.action.replace(
        "/update/",
        "/delete/"
    );

    form.submit();

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
