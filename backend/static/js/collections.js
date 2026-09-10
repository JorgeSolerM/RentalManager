document.addEventListener('change', (event) => {
    const toggle = event.target.closest('[data-select-all]');
    if (!toggle || !toggle.form) return;
    for (const input of toggle.form.elements) {
        if (input.name === toggle.dataset.selectAll && !input.disabled) {
            input.checked = toggle.checked;
        }
    }
});

for (const editor of document.querySelectorAll('[data-collection-name]')) {
    const title = editor.querySelector('[data-name-title]');
    const edit = editor.querySelector('[data-name-edit]');
    const form = editor.querySelector('[data-name-form]');
    const input = form.elements.namedItem('name');
    const cancel = editor.querySelector('[data-name-cancel]');
    edit.hidden = false;
    const discard = () => {
        form.reset();
        form.hidden = true;
        title.hidden = false;
        edit.focus();
    };
    edit.addEventListener('click', () => {
        title.hidden = true;
        form.hidden = false;
        input.focus();
        input.select();
    });
    cancel.addEventListener('click', discard);
    form.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') {
            event.preventDefault();
            event.stopPropagation();
            discard();
        }
    });
    // Enter uses native form submission, including validation and the existing
    // server-side rename contract. No banking state is modified by this editor.
}

const periodInput = document.getElementById('period');
const collectionDateInput = document.getElementById('collection-date');
if (periodInput && collectionDateInput) {
    const today = collectionDateInput.value;
    let explicitDate = false;
    collectionDateInput.addEventListener('input', () => { explicitDate = true; });
    periodInput.addEventListener('change', () => {
        if (!explicitDate && /^\d{4}-\d{2}$/.test(periodInput.value)) {
            const monthStart = `${periodInput.value}-01`;
            collectionDateInput.value = monthStart > today ? monthStart : today;
        }
    });
}
