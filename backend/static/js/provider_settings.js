(() => {
  const feedback = document.querySelector('[data-category-feedback], [data-provider-feedback]');
  const isProvider = input => input.dataset.providerName !== undefined;
  function render(input, active) {
    input.checked = active;
    input.setAttribute('aria-checked', String(active));
    const provider = isProvider(input);
    input.setAttribute('aria-label', `${active ? 'Desactivar' : 'Activar'} ${provider ? 'proveedor' : 'categoría'} ${provider ? input.dataset.providerName : input.dataset.categoryName}`);
    const row = input.closest(provider ? '[data-provider-row]' : '[data-category-row]');
    row.querySelector(provider ? '[data-provider-name]' : '[data-category-name]').classList.toggle('text-secondary', !active);
    row.querySelector(provider ? '[data-provider-category]' : '[data-category-order]').classList.toggle('text-secondary', !active);
  }
  document.querySelectorAll('[data-category-active], [data-provider-active]').forEach(input => {
    input.addEventListener('rm-switch-change', async event => {
      const previous = input.getAttribute('aria-checked') === 'true';
      const requested = event.detail.checked;
      input.disabled = true;
      try {
        const response = await fetch(input.dataset.url, {
          method: 'POST', headers: {Accept: 'application/json'},
          body: new URLSearchParams({active: requested ? '1' : '0'})
        });
        if (!response.ok) throw new Error('category-save');
        const result = await response.json();
        if (typeof result.active !== 'boolean') throw new Error('category-response');
        render(input, result.active);
        const message = isProvider(input)
          ? (result.active ? 'Proveedor activado.' : 'Proveedor desactivado.')
          : (result.active ? 'Categoría activada.' : 'Categoría desactivada.');
        feedback.textContent = message;
        RMToast.success(message, 80);
      } catch (error) {
        render(input, previous);
        const message = `No se pudo cambiar ${isProvider(input) ? 'el proveedor' : 'la categoría'}. Revisa la conexión y vuelve a intentarlo.`;
        feedback.textContent = message;
        RMToast.error(message, 80);
      } finally {
        input.disabled = false;
      }
    });
  });
})();
