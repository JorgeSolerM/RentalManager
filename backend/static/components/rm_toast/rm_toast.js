class RMToast {

    static show(type, message) {

        const container = document.getElementById("rm-toast-container");

        if (!container) {
            console.error("RMToast: no existe #rm-toast-container");
            return;
        }

        const toast = document.createElement("div");

        toast.className = `rm-toast rm-toast-${type}`;

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

            <div class="rm-toast-icon">
                ${icon}
            </div>

            <div class="rm-toast-message">
                ${message}
            </div>

        `;

        container.appendChild(toast);

        let timeout = setTimeout(removeToast, 4000);

        toast.addEventListener("mouseenter", () => {

            clearTimeout(timeout);

        });

        toast.addEventListener("mouseleave", () => {

            timeout = setTimeout(removeToast, 2000);

        });

        function removeToast() {

            toast.classList.add("rm-toast-hide");

            setTimeout(() => {

                toast.remove();

            }, 400);

        }

    }

    static success(message) {

        this.show("success", message);

    }

    static info(message) {

        this.show("info", message);

    }

    static warning(message) {

        this.show("warning", message);

    }

    static error(message) {

        this.show("error", message);

    }

}
