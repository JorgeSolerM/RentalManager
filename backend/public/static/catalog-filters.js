(() => {
    const form = document.querySelector(".catalog-filters");
    if (!form) return;

    const sortSelect = document.querySelector("[data-catalog-sort]");
    sortSelect?.addEventListener("change", () => sortSelect.form.requestSubmit());

    const openControls = [];
    const positionPanel = (toggle, panel) => {
        const trigger = toggle.getBoundingClientRect();
        const panelHeight = panel.offsetHeight;
        const roomBelow = window.innerHeight - trigger.bottom;
        panel.classList.toggle("opens-upward", roomBelow < panelHeight + 12 && trigger.top > panelHeight + 12);
    };
    const registerControl = (root, toggle, panel, onOpen) => {
        const setOpen = (open, restoreFocus = false) => {
            panel.hidden = !open;
            toggle.setAttribute("aria-expanded", String(open));
            panel.classList.remove("opens-upward");
            if (open) {
                openControls.forEach((control) => {
                    if (control.root !== root) control.setOpen(false);
                });
                onOpen?.();
                requestAnimationFrame(() => positionPanel(toggle, panel));
            } else if (restoreFocus) toggle.focus();
        };
        const control = {root, toggle, panel, setOpen};
        openControls.push(control);
        return control;
    };

    const featurePicker = document.querySelector("[data-feature-picker]");
    if (featurePicker) {
        const toggle = featurePicker.querySelector(".feature-picker-toggle");
        const panel = featurePicker.querySelector(".feature-picker-panel");
        const summary = featurePicker.querySelector("[data-feature-summary]");
        const checkboxes = Array.from(panel.querySelectorAll('input[type="checkbox"]'));
        const featureControl = registerControl(featurePicker, toggle, panel);
        const updateSummary = () => {
            const selected = checkboxes.filter((checkbox) => checkbox.checked);
            summary.textContent = selected.length === 0
                ? "Elige características"
                : selected.length === 1
                    ? selected[0].dataset.featureName
                    : `${selected.length} características`;
        };
        toggle.addEventListener("click", () => featureControl.setOpen(panel.hidden));
        checkboxes.forEach((checkbox) => checkbox.addEventListener("change", updateSummary));
        updateSummary();
    }

    const monthNames = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"];
    const weekdayNames = ["L", "M", "X", "J", "V", "S", "D"];
    const pad = (value) => String(value).padStart(2, "0");
    const startOfDay = (date) => new Date(date.getFullYear(), date.getMonth(), date.getDate());
    const addDays = (date, days) => new Date(date.getFullYear(), date.getMonth(), date.getDate() + days);
    const parseISO = (value) => {
        if (!/^\d{4}-\d{2}-\d{2}$/.test(value || "")) return null;
        const [year, month, day] = value.split("-").map(Number);
        const date = new Date(year, month - 1, day);
        return date.getFullYear() === year && date.getMonth() === month - 1 && date.getDate() === day ? date : null;
    };
    const toISO = (date) => `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
    const formatDate = (date) => `${pad(date.getDate())}/${pad(date.getMonth() + 1)}/${date.getFullYear()}`;
    const parseDisplayDate = (value) => {
        const match = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(value || "");
        if (!match) return null;
        const [, dayText, monthText, yearText] = match;
        const day = Number(dayText), month = Number(monthText), year = Number(yearText);
        const date = new Date(year, month - 1, day);
        return date.getFullYear() === year && date.getMonth() === month - 1 && date.getDate() === day ? date : null;
    };
    const maskDate = (value) => {
        const digits = value.replace(/\D/g, "").slice(0, 8);
        if (digits.length < 2) return digits;
        if (digits.length === 2) return `${digits}/`;
        if (digits.length < 4) return `${digits.slice(0, 2)}/${digits.slice(2)}`;
        if (digits.length === 4) return `${digits.slice(0, 2)}/${digits.slice(2)}/`;
        return `${digits.slice(0, 2)}/${digits.slice(2, 4)}/${digits.slice(4)}`;
    };
    const sameDate = (left, right) => left && right && toISO(left) === toISO(right);
    const today = startOfDay(new Date());
    const datePickers = {};

    const createDatePicker = (root) => {
        const role = root.dataset.dateRole;
        const valueInput = root.querySelector("[data-date-value]");
        const textInput = root.querySelector("[data-date-input]");
        const inputShell = root.querySelector(".date-input-shell");
        const error = root.querySelector(".date-picker-error");
        const toggle = root.querySelector(".date-picker-toggle");
        const panel = root.querySelector(".date-picker-panel");
        let selected = parseISO(valueInput.value);
        let viewDate = selected || today;
        const minimumDate = () => role === "check-out" && datePickers["check-in"]?.getSelected()
            ? addDays(datePickers["check-in"].getSelected(), 1)
            : today;
        const updateDisplay = () => {
            textInput.value = selected ? formatDate(selected) : "";
        };
        const setError = (message = "") => {
            error.textContent = message;
            error.hidden = !message;
            inputShell.classList.toggle("has-error", Boolean(message));
            textInput.setAttribute("aria-invalid", String(Boolean(message)));
        };
        const clearValue = () => {
            selected = null;
            valueInput.value = "";
        };
        const validateManual = (showIncompleteError = false) => {
            const value = textInput.value.trim();
            if (!value) {
                clearValue();
                setError();
                return true;
            }
            const date = parseDisplayDate(value);
            if (!date) {
                clearValue();
                if (showIncompleteError || value.replace(/\D/g, "").length === 8) setError("Introduce una fecha válida (DD/MM/AAAA).");
                else setError();
                return false;
            }
            if (date < today) {
                clearValue();
                setError("La fecha no puede estar en el pasado.");
                return false;
            }
            const entry = datePickers["check-in"]?.getSelected();
            if (role === "check-out" && entry && date <= entry) {
                clearValue();
                setError("La salida debe ser posterior a la entrada.");
                return false;
            }
            selected = date;
            valueInput.value = toISO(date);
            setError();
            if (role === "check-in") {
                const checkOut = datePickers["check-out"];
                if (checkOut?.getSelected() && checkOut.getSelected() <= date) checkOut.clear();
            }
            return true;
        };
        const focusDate = (date) => panel.querySelector(`[data-calendar-date="${toISO(date)}"]`)?.focus({preventScroll: true});

        const selectDate = (date) => {
            selected = date;
            valueInput.value = toISO(date);
            setError();
            updateDisplay();
            if (role === "check-in") {
                const checkOut = datePickers["check-out"];
                if (checkOut?.getSelected() && checkOut.getSelected() <= date) checkOut.clear();
                control.setOpen(false);
                window.setTimeout(() => checkOut?.open(), 0);
            } else control.setOpen(false, true);
        };

        const render = () => {
            const year = viewDate.getFullYear();
            const month = viewDate.getMonth();
            const min = minimumDate();
            const first = new Date(year, month, 1);
            const daysInMonth = new Date(year, month + 1, 0).getDate();
            const leading = (first.getDay() + 6) % 7;
            const previousMonthEnd = new Date(year, month, 0);
            const previousDisabled = previousMonthEnd < new Date(min.getFullYear(), min.getMonth(), 1);
            if (!panel.querySelector(".date-picker-header")) {
                panel.innerHTML = `
                    <div class="date-picker-header">
                        <button type="button" class="date-picker-nav" data-calendar-previous aria-label="Mes anterior">‹</button>
                        <strong></strong>
                        <button type="button" class="date-picker-nav" data-calendar-next aria-label="Mes siguiente">›</button>
                    </div>
                    <div class="date-picker-weekdays" aria-hidden="true">${weekdayNames.map((day) => `<span>${day}</span>`).join("")}</div>
                    <div class="date-picker-days" role="grid"></div>`;
                panel.querySelector("[data-calendar-previous]").addEventListener("click", () => {
                    viewDate = new Date(viewDate.getFullYear(), viewDate.getMonth() - 1, 1);
                    render();
                });
                panel.querySelector("[data-calendar-next]").addEventListener("click", () => {
                    viewDate = new Date(viewDate.getFullYear(), viewDate.getMonth() + 1, 1);
                    render();
                });
            }
            panel.querySelector(".date-picker-header strong").textContent = `${monthNames[month]} ${year}`;
            panel.querySelector("[data-calendar-previous]").disabled = previousDisabled;
            const days = panel.querySelector(".date-picker-days");
            days.replaceChildren();
            for (let index = 0; index < leading; index += 1) {
                const blank = document.createElement("span");
                blank.className = "date-picker-blank";
                days.appendChild(blank);
            }
            for (let day = 1; day <= daysInMonth; day += 1) {
                const date = new Date(year, month, day);
                const button = document.createElement("button");
                button.type = "button";
                button.className = "date-picker-day";
                button.textContent = String(day);
                button.dataset.calendarDate = toISO(date);
                button.setAttribute("role", "gridcell");
                button.setAttribute("aria-label", formatDate(date));
                button.disabled = date < min;
                if (sameDate(date, today)) {
                    button.classList.add("is-today");
                    button.setAttribute("aria-current", "date");
                }
                if (sameDate(date, selected)) {
                    button.classList.add("is-selected");
                    button.setAttribute("aria-selected", "true");
                }
                days.appendChild(button);
            }
            for (let index = leading + daysInMonth; index < 42; index += 1) {
                const blank = document.createElement("span");
                blank.className = "date-picker-blank";
                days.appendChild(blank);
            }
            panel.querySelectorAll("[data-calendar-date]").forEach((button) => {
                button.addEventListener("click", () => selectDate(parseISO(button.dataset.calendarDate)));
            });
        };

        const control = registerControl(root, toggle, panel, () => {
            validateManual(false);
            const min = minimumDate();
            viewDate = selected && selected >= min ? selected : min;
            render();
            requestAnimationFrame(() => focusDate(selected && selected >= min ? selected : min));
        });
        toggle.addEventListener("click", () => control.setOpen(panel.hidden));
        textInput.addEventListener("input", (event) => {
            const deleting = event.inputType?.startsWith("delete");
            textInput.value = deleting
                ? textInput.value.replace(/[^\d/]/g, "").slice(0, 10)
                : maskDate(textInput.value);
            clearValue();
            setError();
            if (textInput.value.replace(/\D/g, "").length === 8) validateManual(false);
        });
        textInput.addEventListener("blur", () => validateManual(Boolean(textInput.value.trim())));
        panel.addEventListener("keydown", (event) => {
            const active = event.target.closest?.("[data-calendar-date]");
            if (!active || !["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) return;
            event.preventDefault();
            const delta = {ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7}[event.key];
            let target = addDays(parseISO(active.dataset.calendarDate), delta);
            const min = minimumDate();
            if (target < min) target = min;
            if (target.getMonth() !== viewDate.getMonth() || target.getFullYear() !== viewDate.getFullYear()) {
                viewDate = new Date(target.getFullYear(), target.getMonth(), 1);
                render();
            }
            focusDate(target);
        });
        updateDisplay();
        return {
            clear: () => {
                clearValue();
                setError();
                updateDisplay();
            },
            getSelected: () => selected,
            open: () => control.setOpen(true),
            validate: () => validateManual(Boolean(textInput.value.trim())),
            focus: () => textInput.focus(),
        };
    };

    document.querySelectorAll("[data-date-picker]").forEach((root) => {
        datePickers[root.dataset.dateRole] = createDatePicker(root);
    });
    form.addEventListener("submit", (event) => {
        const invalid = [datePickers["check-in"], datePickers["check-out"]].find((picker) => !picker.validate());
        if (invalid) {
            event.preventDefault();
            invalid.focus();
        }
    });
    document.addEventListener("keydown", (event) => {
        if (event.key !== "Escape") return;
        const active = openControls.find((control) => !control.panel.hidden);
        if (active) {
            event.preventDefault();
            active.setOpen(false, true);
        }
    });
    document.addEventListener("click", (event) => {
        const eventPath = event.composedPath();
        openControls.forEach((control) => {
            if (!control.panel.hidden && !eventPath.includes(control.root)) control.setOpen(false);
        });
    });
})();
