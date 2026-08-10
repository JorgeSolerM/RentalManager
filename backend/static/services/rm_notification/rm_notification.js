class RMNotification {

    // ==========================================================
    // Configuración
    // ==========================================================

    static TOP_MARGIN = 24;

    static SLOT_HEIGHT = 92;

    static APPEAR_DELAY = 350;


    // ==========================================================
    // Estado
    // ==========================================================

    static nextSlot = 0;

    static activeToasts = 0;

    static nextAppearanceTime = 0;


    // ==========================================================
    // API pública
    // ==========================================================

    static success(message) {

        this.enqueue("success", message);

    }

    static info(message) {

        this.enqueue("info", message);

    }

    static warning(message) {

        this.enqueue("warning", message);

    }

    static error(message) {

        this.enqueue("error", message);

    }


    // ==========================================================
    // Cola de aparición
    // ==========================================================

    static enqueue(type, message) {

        const slot = this.nextSlot++;

        const top = this.TOP_MARGIN + slot * this.SLOT_HEIGHT;

        this.activeToasts++;

        const now = Date.now();

        if (this.nextAppearanceTime < now) {

            this.nextAppearanceTime = now;

        }

        const delay = this.nextAppearanceTime - now;

        this.nextAppearanceTime += this.APPEAR_DELAY;

        setTimeout(() => {

            this.show(type, message, top);

        }, delay);

    }


    // ==========================================================
    // Mostrar
    // ==========================================================

    static show(type, message, top) {

        const onRemoved = () => {

            this.activeToasts--;

            if (this.activeToasts === 0) {

                this.nextSlot = 0;

                this.nextAppearanceTime = 0;

            }

        };

        switch (type) {

            case "success":

                RMToast.success(message, top, onRemoved);

                break;

            case "info":

                RMToast.info(message, top, onRemoved);

                break;

            case "warning":

                RMToast.warning(message, top, onRemoved);

                break;

            case "error":

                RMToast.error(message, top, onRemoved);

                break;

        }

    }

}
