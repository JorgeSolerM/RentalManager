const PHOTO_UPLOAD_CONCURRENCY = 3;

document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("[data-photo-upload-form]").forEach((form) => {
        const input = form.querySelector("[data-photo-input]");
        const selectButton = form.querySelector("[data-photo-select-button]");
        const summary = form.querySelector("[data-photo-selection-summary]");
        const list = form.querySelector("[data-photo-selection-list]");
        let running = false;

        const setLocked = (locked) => {
            input.disabled = locked;
            selectButton.classList.toggle("disabled", locked);
            selectButton.setAttribute("aria-disabled", locked ? "true" : "false");
            form.toggleAttribute("aria-busy", locked);
        };

        const renderItem = (entry) => {
            const labels = {
                pending: ["○", "Pendiente"],
                uploading: ["○", "Subiendo"],
                completed: ["✓", "Completado"],
                error: ["⚠", "Error al subir"],
            };
            const [icon, label] = labels[entry.status];
            entry.element.dataset.uploadStatus = entry.status;
            const iconElement = document.createElement("span");
            iconElement.className = "rm-photo-upload-icon";
            iconElement.textContent = icon;
            const nameElement = document.createElement(entry.status === "completed" ? "strong" : "span");
            nameElement.className = "rm-photo-upload-name";
            nameElement.textContent = entry.file.name;
            const statusElement = document.createElement("span");
            statusElement.className = "rm-photo-upload-state";
            statusElement.textContent = ` · ${label}`;
            entry.element.replaceChildren(iconElement, document.createTextNode(" "), nameElement, statusElement);
        };

        const updateSummary = (entries) => {
            const completed = entries.filter((entry) => entry.status === "completed").length;
            const errors = entries.filter((entry) => entry.status === "error").length;
            const active = entries.length - completed - errors;
            if (active > 0) {
                summary.textContent = `Subiendo ${entries.length} ${entries.length === 1 ? "imagen" : "imágenes"}…`;
            } else if (errors > 0) {
                summary.textContent = `${completed} ${completed === 1 ? "subida" : "subidas"} · ${errors} con error`;
            } else {
                summary.textContent = `${completed} ${completed === 1 ? "imagen subida" : "imágenes subidas"}`;
            }
        };

        const uploadOne = async (entry, entries) => {
            entry.status = "uploading";
            renderItem(entry);
            const payload = new FormData();
            payload.append("files", entry.file, entry.file.name);
            try {
                const response = await fetch(form.action, { method: "POST", body: payload, redirect: "follow" });
                const finalUrl = new URL(response.url || window.location.href, window.location.origin);
                if (!response.ok || finalUrl.searchParams.has("error")) {
                    throw new Error(finalUrl.searchParams.get("error") || `upload_failed_${response.status}`);
                }
                entry.status = "completed";
            } catch (error) {
                entry.status = "error";
            }
            renderItem(entry);
            updateSummary(entries);
        };

        const runQueue = async (files) => {
            if (running || files.length === 0) return;
            running = true;
            setLocked(true);
            list.replaceChildren();
            const entries = files.map((file) => {
                const element = document.createElement("li");
                list.appendChild(element);
                const entry = { file, element, status: "pending" };
                renderItem(entry);
                return entry;
            });
            updateSummary(entries);

            let nextIndex = 0;
            const worker = async () => {
                while (nextIndex < entries.length) {
                    const entry = entries[nextIndex];
                    nextIndex += 1;
                    await uploadOne(entry, entries);
                }
            };
            const workerCount = Math.min(PHOTO_UPLOAD_CONCURRENCY, entries.length);
            await Promise.all(Array.from({ length: workerCount }, () => worker()));

            running = false;
            input.value = "";
            setLocked(false);
            const hasErrors = entries.some((entry) => entry.status === "error");
            if (!hasErrors) window.setTimeout(() => window.location.reload(), 800);
        };

        input.addEventListener("change", () => {
            if (running) return;
            const files = Array.from(input.files || []);
            void runQueue(files);
        });
        form.addEventListener("submit", (event) => event.preventDefault());
        setLocked(false);
    });
});
