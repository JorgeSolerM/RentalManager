document.addEventListener("DOMContentLoaded", () => {

    const params = new URLSearchParams(
        window.location.search
    );

    const success = params.get(
        "success"
    );

    if (!success) {

        return;

    }

    const SUCCESS_MESSAGES = {

        platform_created:
            "Plataforma creada.",

        platform_updated:
            "Plataforma actualizada.",

        platform_deleted:
            "Plataforma eliminada."

    };

    console.log(
        "Mensaje:",
        SUCCESS_MESSAGES[success]
    );

    RMNotification.success(
        SUCCESS_MESSAGES[success]
    );

    params.delete(
        "success"
    );

    const query = params.toString();

    const url = query
        ? `${window.location.pathname}?${query}`
        : window.location.pathname;

    console.log(
        "Nueva URL:",
        url
    );

    history.replaceState(
        {},
        "",
        url
    );

});

function openCreatePlatformModal() {

    document.getElementById("platform-modal-title").textContent =
        "Nueva plataforma";

    document.getElementById("platform-submit-button").textContent =
        "Guardar";

    document.getElementById("platform-form").action =
        "/settings/platforms/create";

    document
        .getElementById("platform-delete-button")
        .classList.add("hidden");

    clearPlatformForm();

    document
        .getElementById("platform-modal")
        .classList.remove("hidden");

}


function closePlatformModal() {

    document
        .getElementById("platform-modal")
        .classList.add("hidden");

}


function clearPlatformForm() {

    document
        .getElementById("platform-form")
        .reset();

}
