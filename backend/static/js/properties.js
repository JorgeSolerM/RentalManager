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

    document.getElementById("property-location-button")?.classList.add("hidden");

    document
        .getElementById("property-form")
        .reset();

    document
        .getElementById("property-legacy-address")
        .classList.add("hidden");

    document.getElementById("property-legacy-address-value").textContent = "";

}


function fillPropertyForm(property) {

    const locationButton = document.getElementById("property-location-button");
    if (locationButton) {
        locationButton.dataset.propertyId = property.id;
        locationButton.dataset.address = JSON.stringify(
            [property.street, property.street_number, property.city].map(value => (value ?? "").trim())
        );
        locationButton.classList.remove("hidden");
    }

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


async function updatePropertyLocation() {
    const button = document.getElementById("property-location-button");
    if (!button?.dataset.propertyId || button.disabled) return;
    const address = JSON.stringify(["street", "street_number", "city"].map(
        id => document.getElementById(id).value.trim()
    ));
    if (address !== button.dataset.address) {
        RMNotification.error("Guarda primero los cambios de dirección y vuelve a abrir la finca para actualizar su ubicación.");
        return;
    }
    button.disabled = true;
    try {
        const url = `/properties/${button.dataset.propertyId}/geolocation`;
        const response = await fetch(url, { credentials: "same-origin" });
        if (!response.ok) throw new Error("review_unavailable");
        const page = new DOMParser().parseFromString(await response.text(), "text/html");
        const token = page.querySelector('input[name="csrf"]')?.value;
        if (!token) throw new Error("review_token_missing");
        const form = document.createElement("form");
        form.method = "post";
        form.action = `${url}/retry`;
        const csrf = document.createElement("input");
        csrf.type = "hidden"; csrf.name = "csrf"; csrf.value = token;
        form.append(csrf); document.body.append(form);
        form.submit();
    } catch (_error) {
        RMNotification.error("No se ha podido abrir la actualización de ubicación. Inténtalo de nuevo.");
        button.disabled = false;
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
