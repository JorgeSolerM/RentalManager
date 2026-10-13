(() => {
    const departure = document.getElementById('effectiveDeparture');
    const economic = document.getElementById('economicLastDay');
    if (!departure || !economic) return;
    let edited = Boolean(economic.value);
    economic.addEventListener('input', () => { edited = Boolean(economic.value); });
    departure.addEventListener('change', () => {
        if (!edited) economic.value = departure.value;
    });
    const form = document.getElementById('earlyTerminationForm');
    const confirmation = document.getElementById('earlyTerminationConfirmation');
    const notice = document.getElementById('earlyTerminationStaleNotice');
    if (form && confirmation) {
        const invalidate = () => {
            confirmation.hidden = true;
            if (notice) notice.hidden = false;
        };
        form.addEventListener('input', invalidate);
        form.addEventListener('change', invalidate);
        // This control belongs to the form through its form attribute,
        // but sits beside the preview warning, outside the form's DOM tree.
        document.getElementById('acceptProration')?.addEventListener('change', invalidate);
    }
})();
