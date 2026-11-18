document.querySelector('[data-geo-edit]')?.addEventListener('click', async function () {
    await editProperty(this.dataset.geoEdit);
    const modal = document.getElementById('property-modal');
    if (modal.classList.contains('hidden')) return;
    const form = document.getElementById('property-form');
    form.action = `/properties/${this.dataset.geoEdit}/geolocation/address`;
    let token = form.querySelector('[name="csrf"]');
    if (!token) { token = document.createElement('input'); token.type = 'hidden'; token.name = 'csrf'; form.append(token); }
    token.value = this.dataset.geoCsrf;
    document.getElementById('property-delete-button').classList.add('hidden');
    document.getElementById('street').focus();
});
