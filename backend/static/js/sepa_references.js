document.querySelectorAll('[data-generate-reference]').forEach(button => {
    const form = button.closest('form');
    const creditor = form.elements.creditor_profile_id;
    const reference = form.elements.mandate_reference;
    const status = form.querySelector('[data-reference-status]');
    const refresh = () => { button.disabled = !creditor.value; };
    creditor.addEventListener('change', refresh);
    refresh();
    button.addEventListener('click', async () => {
        if (!creditor.value) return;
        if (reference.value && !window.confirm('¿Sustituir la referencia escrita por una nueva?')) return;
        const selectedCreditor = creditor.value;
        button.disabled = true;
        creditor.disabled = true;
        try {
            const response = await fetch('/sepa/references', {
                method: 'POST', body: new URLSearchParams({creditor_profile_id: selectedCreditor})
            });
            if (!response.ok) throw new Error('No se ha podido generar la referencia. Revisa el acreedor e inténtalo de nuevo.');
            const data = await response.json();
            reference.value = data.reference;
            status.textContent = 'Referencia generada. Puedes editarla antes de guardar.';
            reference.focus();
        } catch (error) {
            status.textContent = error.message;
        } finally {
            creditor.disabled = false;
            refresh();
        }
    });
});
document.querySelectorAll('[data-new-mandate]').forEach(button => {
    button.addEventListener('click', () => {
        const form = document.getElementById('new-sepa-mandate');
        form.open = true;
        form.scrollIntoView({block: 'start'});
        form.querySelector('select').focus();
    });
});
