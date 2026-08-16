document.addEventListener("DOMContentLoaded", () => {
    const deleteButton = document.getElementById(
        "platform-delete-button"
    );

    if (deleteButton) {

        deleteButton.addEventListener(
            "click",
            handleDeletePlatform,
        );

    }

});

function openCreatePlatformModal() {

    document.getElementById(
        "platform-modal-title"
    ).textContent =
        "Nueva plataforma";

    document.getElementById(
        "platform-submit-button"
    ).textContent =
        "Guardar";

    document.getElementById(
        "platform-form"
    ).action =
        "/settings/platforms/create";

    document.getElementById(
        "platform-delete-button"
    ).classList.add(
        "hidden"
    );

    clearPlatformForm();

    document.getElementById(
        "platform-modal"
    ).classList.remove(
        "hidden"
    );

}

async function openEditPlatformModal(
    platformId
) {

    try {

        const response = await fetch(
            `/settings/platforms/edit/${platformId}`
        );

        if (!response.ok) {

            throw new Error();

        }

        const platform =
            await response.json();

        document.getElementById(
            "platform-modal-title"
        ).textContent =
            "Editar plataforma";

        document.getElementById(
            "platform-submit-button"
        ).textContent =
            "Guardar cambios";

        document.getElementById(
            "platform-form"
        ).action =
            `/settings/platforms/update/${platform.id}`;

        document.getElementById(
            "platform-name"
        ).value =
            platform.name;

        document.getElementById(
            "platform-slug"
        ).value =
            platform.slug;

        document.getElementById(
            "platform-import"
        ).checked =
            platform.supports_import;

        document.getElementById(
            "platform-export"
        ).checked =
            platform.supports_export;

        const deleteButton =
            document.getElementById(
                "platform-delete-button"
            );

        deleteButton.classList.remove(
            "hidden"
        );

        deleteButton.dataset.platformId =
            platform.id;

        document.getElementById(
            "platform-modal"
        ).classList.remove(
            "hidden"
        );

    } catch (error) {

        console.error(error);

        RMNotification.error(
            "No se ha podido cargar la plataforma."
        );

    }

}

function handleDeletePlatform() {

    if (!RMConfirm.ask(
        "¿Desea eliminar esta plataforma?"
    )) {

        return;

    }

    const form =
        document.getElementById(
            "platform-form"
        );

    const platformId =
        document.getElementById(
            "platform-delete-button"
        ).dataset.platformId;

    form.action =
        `/settings/platforms/delete/${platformId}`;

    form.submit();

}

function closePlatformModal() {

    document.getElementById(
        "platform-modal"
    ).classList.add(
        "hidden"
    );

}

function clearPlatformForm() {

    document.getElementById(
        "platform-form"
    ).reset();

}
