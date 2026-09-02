document.addEventListener("DOMContentLoaded", () => {
    initializePropertySwitches();

});

let propertyEditPending = false;


function openCreatePropertyModal() {

    document.getElementById("property-modal-title").textContent =
        "Nueva propiedad";

    document.getElementById("property-modal-submit").textContent =
        "Guardar";

    document.getElementById("property-form").action =
        "/properties/create";

    document.getElementById(
        "property-delete-button"
    ).classList.add(
        "hidden"
    );

    clearPropertyForm();

    document
        .getElementById("property-modal")
        .classList.remove("hidden");

}


function closePropertyModal() {

    document
        .getElementById("property-modal")
        .classList.add("hidden");

}


function clearPropertyForm() {

    document
        .getElementById("property-form")
        .reset();

    document
        .getElementById("property-legacy-address")
        .classList.add("hidden");

    document.getElementById("property-legacy-address-value").textContent = "";

}


function fillPropertyForm(property) {

    document.getElementById("name").value =
        property.name ?? "";

    document.getElementById("alias").value =
        property.alias ?? "";

    document.getElementById("street").value = property.street ?? "";
    document.getElementById("street_number").value = property.street_number ?? "";
    document.getElementById("floor").value = property.floor ?? "";
    document.getElementById("door").value = property.door ?? "";

    const legacyAddress = document.getElementById("property-legacy-address");
    const legacyAddressValue = document.getElementById("property-legacy-address-value");
    const showLegacyAddress = !property.street && Boolean(property.address);
    legacyAddress.classList.toggle("hidden", !showLegacyAddress);
    legacyAddressValue.textContent = showLegacyAddress ? property.address : "";

    document.getElementById("city").value =
        property.city ?? "";

    document.getElementById("notes").value =
        property.notes ?? "";

}


async function editProperty(propertyId) {

    if (propertyEditPending) {
        return;
    }

    propertyEditPending = true;

    try {

        const response = await fetch(
            `/properties/${propertyId}`
        );

        if (!response.ok) {

            RMNotification.error(
                "No se ha podido cargar la propiedad."
            );

            return;

        }

        const property = await response.json();

        document.getElementById("property-modal-title").textContent =
            "Editar propiedad";

        document.getElementById("property-modal-submit").textContent =
            "Actualizar";

        document.getElementById("property-form").action =
            `/properties/update/${propertyId}`;

        document.getElementById(
            "property-delete-button"
        ).classList.remove(
            "hidden"
        );

        document.getElementById(
            "property-delete-button"
        ).dataset.propertyId =
            propertyId;

        fillPropertyForm(property);

        document
            .getElementById("property-modal")
            .classList.remove("hidden");

    }

    catch (error) {

        console.error(error);

        RMNotification.error(
            "Error de comunicación con el servidor."
        );

    }

    finally {

        propertyEditPending = false;

    }

}


function deleteProperty() {

    if (!RMConfirm.ask(
        "¿Desea eliminar esta propiedad?"
    )) {

        return;

    }

    const form =
        document.getElementById(
            "property-form"
        );

    const propertyId =
        document.getElementById(
            "property-delete-button"
        ).dataset.propertyId;

    form.action =
        `/properties/delete/${propertyId}`;

    form.submit();

}


function initializePropertySwitches() {

    const switches = document.querySelectorAll(".rm-switch-input");

    switches.forEach((element) => {

        element.addEventListener("change", async () => {

            const propertyId = element.dataset.propertyId;

            try {

                const response = await fetch(

                    `/properties/toggle/${propertyId}`,

                    {
                        method: "POST"
                    }

                );

                if (!response.ok) {

                    throw new Error();

                }

                const result = await response.json();

                if (result.active) {

                    RMNotification.success(
                        "Propiedad activada."
                    );

                }

                else {

                    RMNotification.success(
                        "Propiedad desactivada."
                    );

                }

            }

            catch (error) {

                console.error(error);

                element.checked = !element.checked;

                RMNotification.error(
                    "No se ha podido actualizar la propiedad."
                );

            }

        });

    });

}
