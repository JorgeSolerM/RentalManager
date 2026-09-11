(() => {
  const tabs = document.querySelectorAll('[data-nf-tab]');
  tabs.forEach(button => button.addEventListener('click', () => {
    tabs.forEach(tab => tab.setAttribute('aria-pressed', String(tab === button)));
    document.querySelectorAll('[data-nf-panel]').forEach(panel => {
      panel.hidden = panel.dataset.nfPanel !== button.dataset.nfTab;
    });
  }));
  document.querySelector('#nf-filter')?.addEventListener('change', event => {
    if (event.target.value === 'Datos completables') document.querySelector('[data-nf-tab="people"]')?.click();
    document.querySelectorAll('[data-nf-row]').forEach(row => {
      row.hidden = !!event.target.value && !row.dataset.nfRow.includes(event.target.value);
    });
  });
  document.querySelectorAll('[data-nf-selection]').forEach(box => box.addEventListener('change', () => {
    document.querySelector('#nf-selected').textContent = `${document.querySelectorAll('[data-nf-selection]:checked').length} registros seleccionados (incluye otras pestañas/filtros).`;
  }));
  document.querySelectorAll('[data-nf-target]').forEach(select => select.addEventListener('change', async () => {
    const card = select.closest('[data-nf-person]');
    const form = select.form;
    const status = card.querySelector('[data-nf-comparison-status]');
    const chosen = select.value;
    const serial = String(Number(card.dataset.request || 0) + 1);
    card.dataset.request = serial;
    card.querySelectorAll('[data-nf-field-check]').forEach(box => { box.checked = false; box.disabled = true; });
    status.textContent = chosen ? 'Comparando el destino seleccionado…' : 'Elija un destino; no hay campos habilitados.';
    if (!chosen) return;
    const data = new FormData();
    ['csrf', 'token'].forEach(name => data.set(name, form.elements[name].value));
    data.set('source_id', card.dataset.nfPerson); data.set('target_id', chosen);
    data.set('phone_source', card.querySelector('[data-nf-phone-source]')?.value || '');
    try {
      const response = await fetch('/reconciliation/netfincas/compare', { method: 'POST', body: data });
      if (!response.ok) throw new Error('comparison');
      const result = await response.json();
      if (card.dataset.request !== serial) return;
      result.fields.forEach(field => {
        const row = card.querySelector(`[data-nf-field="${field.key}"]`);
        row.querySelector('[data-nf-old]').textContent = field.target;
        row.querySelector('[data-nf-new]').textContent = field.source;
        row.querySelector('[data-nf-status]').textContent = field.status === 'Diferente' ? '⚠ Conflicto: no se sobrescribe' : field.status;
        row.classList.toggle('table-warning', field.status === 'Diferente');
        row.querySelector('[data-nf-field-check]').disabled = !field.selectable;
      });
      status.textContent = 'Comparación del destino elegido. Seleccione solo los campos que desea añadir. Ningún conflicto se sobrescribe.';
    } catch (_) { if (card.dataset.request === serial) status.textContent = 'No se pudo comparar. Recargue la revisión antes de continuar.'; }
  }));
  document.querySelectorAll('[data-nf-phone-source]').forEach(select => select.addEventListener('change', () => {
    select.closest('[data-nf-person]').querySelector('[data-nf-target]').dispatchEvent(new Event('change'));
  }));
  document.querySelector('[data-nf-confirm]')?.addEventListener('submit', event => {
    if (!window.confirm('Solo se aplicarán los cambios mostrados en esta revisión. ¿Aplicar cambios?')) event.preventDefault();
  });
  document.querySelectorAll('[data-nf-owner]').forEach(card => {
    const target = card.querySelector('[data-nf-owner-target]');
    const source = card.querySelector('[data-nf-owner-phone-source]');
    const box = card.querySelector('[data-nf-owner-phone-check]');
    const update = () => {
      if (!box) return;
      box.checked = false;
      const informed = target.selectedOptions[0]?.dataset.phoneInformed === 'yes';
      box.disabled = !target.value || informed || (source && !source.value);
      const status = card.querySelector('[data-nf-owner-phone-status]');
      if (status) status.textContent = informed ? 'El teléfono del propietario ya está informado: no se sobrescribe.' : 'Seleccione el teléfono y revise los cambios; no se aplican automáticamente.';
    };
    target.addEventListener('change', update);source?.addEventListener('change', update);
  });
})();
