function openCreatePropertyModal() {

    document.getElementById("property-modal-title").textContent =
        "Nueva propiedad";

    document.getElementById("property-modal-submit").textContent =
        "Guardar";

    document.getElementById("property-form").action =
        "/properties/create";

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

}


function fillPropertyForm(property) {

    document.getElementById("name").value =
        property.name ?? "";

    document.getElementById("alias").value =
        property.alias ?? "";

    document.getElementById("address").value =
        property.address ?? "";

    document.getElementById("city").value =
        property.city ?? "";

    document.getElementById("owner").value =
        property.owner ?? "";

    document.getElementById("notes").value =
        property.notes ?? "";

}


async function editProperty(propertyId) {

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


/* ============================================
   INICIALIZACIÓN
============================================ */

initializePropertySwitches();
