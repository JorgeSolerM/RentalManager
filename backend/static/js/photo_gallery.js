document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("[data-photo-gallery]").forEach((gallery) => {
        let dragged = null;
        let snapshot = null;
        let dropped = false;
        let insertion = null;
        let suppressClickUntil = 0;
        const status = gallery.parentElement.querySelector("[data-photo-order-status]");

        const cards = () => Array.from(gallery.querySelectorAll("[data-photo-card]"));
        const select = (selected) => {
            cards().forEach((card) => card.setAttribute("aria-selected", card === selected ? "true" : "false"));
        };
        const restore = (items) => items.forEach((item) => gallery.appendChild(item));
        const clearInsertion = () => {
            if (!insertion) return;
            insertion.target.classList.remove(
                "rm-photo-card-insert-before", "rm-photo-card-insert-after"
            );
            insertion = null;
        };
        const showInsertion = (target, position) => {
            clearInsertion();
            insertion = { target, position };
            target.classList.add(
                position === "before" ? "rm-photo-card-insert-before" : "rm-photo-card-insert-after"
            );
        };
        const nearestCard = (clientX, clientY) => {
            const candidates = cards().filter((card) => card !== dragged);
            return candidates.reduce((nearest, card) => {
                const rect = card.getBoundingClientRect();
                const dx = clientX < rect.left ? rect.left - clientX
                    : clientX > rect.right ? clientX - rect.right : 0;
                const dy = clientY < rect.top ? rect.top - clientY
                    : clientY > rect.bottom ? clientY - rect.bottom : 0;
                const distance = dx * dx + dy * dy;
                return !nearest || distance < nearest.distance ? { card, distance } : nearest;
            }, null)?.card || null;
        };

        const persist = async (previousOrder) => {
            if (gallery.dataset.reordering === "true") return false;
            const previousIds = previousOrder.map((card) => card.dataset.photoId);
            const currentIds = cards().map((card) => card.dataset.photoId);
            if (previousIds.every((id, index) => id === currentIds[index])) return true;
            gallery.dataset.reordering = "true";
            status.textContent = "Guardando…";
            const photoIds = cards().map((card) => Number(card.dataset.photoId));
            try {
                const response = await fetch(`/photo-order/${gallery.dataset.ownerType}`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ owner_id: Number(gallery.dataset.ownerId), photo_ids: photoIds }),
                });
                if (!response.ok) throw new Error(`photo_order_${response.status}`);
                status.textContent = "";
                return true;
            } catch (error) {
                restore(previousOrder);
                status.textContent = "No se pudo guardar el orden.";
                RMNotification.error("No se pudo guardar el nuevo orden de las fotografías.");
                return false;
            } finally {
                gallery.dataset.reordering = "false";
            }
        };

        gallery.addEventListener("click", (event) => {
            if (performance.now() < suppressClickUntil) {
                event.preventDefault();
                return;
            }
            if (event.target.closest("button, form, a, input")) return;
            const card = event.target.closest("[data-photo-card]");
            select(card && card.getAttribute("aria-selected") !== "true" ? card : null);
        });
        gallery.addEventListener("keydown", async (event) => {
            const card = event.target.closest("[data-photo-card]");
            if (!card) return;
            if ((event.key === "Enter" || event.key === " ") && !event.altKey) {
                event.preventDefault();
                select(card);
                return;
            }
            if (!event.altKey || !["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) return;
            event.preventDefault();
            const previous = cards();
            const index = previous.indexOf(card);
            const backwards = event.key === "ArrowLeft" || event.key === "ArrowUp";
            const targetIndex = backwards ? index - 1 : index + 1;
            if (targetIndex < 0 || targetIndex >= previous.length) return;
            if (backwards) gallery.insertBefore(card, previous[targetIndex]);
            else gallery.insertBefore(previous[targetIndex], card);
            await persist(previous);
            card.focus();
        });
        gallery.addEventListener("dragstart", (event) => {
            dragged = event.target.closest("[data-photo-card]");
            if (!dragged || gallery.dataset.reordering === "true") {
                event.preventDefault();
                return;
            }
            snapshot = cards();
            dropped = false;
            clearInsertion();
            suppressClickUntil = performance.now() + 500;
            select(dragged);
            event.dataTransfer.effectAllowed = "move";
            event.dataTransfer.setData("text/plain", dragged.dataset.photoId);
            dragged.classList.add("rm-photo-card-dragging");
        });
        gallery.addEventListener("dragover", (event) => {
            if (!dragged) return;
            let target = event.target.closest("[data-photo-card]");
            if (!target || target === dragged) target = nearestCard(event.clientX, event.clientY);
            if (!target) return;
            event.preventDefault();
            const rect = target.getBoundingClientRect();
            const position = event.clientY < rect.top ? "before"
                : event.clientY > rect.bottom ? "after"
                : event.clientX < rect.left + rect.width / 2 ? "before" : "after";
            if (!insertion || insertion.target !== target || insertion.position !== position) {
                showInsertion(target, position);
            }
        });
        gallery.addEventListener("drop", async (event) => {
            if (!dragged) return;
            event.preventDefault();
            dropped = true;
            if (insertion) {
                insertion.target[insertion.position](dragged);
            }
            clearInsertion();
            await persist(snapshot);
        });
        gallery.addEventListener("dragend", () => {
            suppressClickUntil = performance.now() + 350;
            if (dragged) dragged.classList.remove("rm-photo-card-dragging");
            clearInsertion();
            if (!dropped && snapshot) restore(snapshot);
            dragged = null;
            snapshot = null;
            dropped = false;
        });
        document.addEventListener("click", (event) => {
            if (!gallery.contains(event.target)) select(null);
        });
    });
});
