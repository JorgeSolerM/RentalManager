class RMToast {

    // ==========================================================
    // Configuración
    // ==========================================================

    static DISPLAY_TIME = 4000;

    static HIDE_DURATION = 500;


    // ==========================================================
    // API pública
    // ==========================================================

    static success(message, top, onRemoved = null) {

        this.render("success", message, top, onRemoved);

    }

    static info(message, top, onRemoved = null) {

        this.render("info", message, top, onRemoved);

    }

    static warning(message, top, onRemoved = null) {

        this.render("warning", message, top, onRemoved);

    }

    static error(message, top, onRemoved = null) {

        this.render("error", message, top, onRemoved);

    }


    // ==========================================================
    // Render
    // ==========================================================

    static render(type, message, top, onRemoved) {

        const container = document.getElementById("rm-toast-container");

        if (!container) {

            console.error("RMToast: no existe #rm-toast-container");

            return;

        }

        const toast = document.createElement("div");

        toast.className = `rm-toast rm-toast-${type}`;

        toast.style.top = `${top}px`;

        let icon = "";

        switch (type) {

            case "success":
                icon = "✔";
                break;

            case "info":
                icon = "ℹ";
                break;

            case "warning":
                icon = "⚠";
                break;

            case "error":
                icon = "✖";
                break;

        }

        toast.innerHTML = `
            <div class="rm-toast-icon">${icon}</div>
            <div class="rm-toast-message">${message}</div>
        `;

        container.appendChild(toast);

        requestAnimationFrame(() => {

            toast.classList.add("rm-toast-show");

        });

        let timeout = setTimeout(() => {

            this.remove(toast, onRemoved);

        }, this.DISPLAY_TIME);

        toast.addEventListener("mouseenter", () => {

            clearTimeout(timeout);

        });

        toast.addEventListener("mouseleave", () => {

            timeout = setTimeout(() => {

                this.remove(toast, onRemoved);

            }, 2000);

        });

    }


    // ==========================================================
    // Remove
    // ==========================================================

    static remove(toast, onRemoved) {

        if (!toast) {

            return;

        }

        toast.classList.remove("rm-toast-show");

        toast.classList.add("rm-toast-hide");

        setTimeout(() => {

            toast.remove();

            if (typeof onRemoved === "function") {

                onRemoved();

            }

        }, this.HIDE_DURATION);

    }

}
