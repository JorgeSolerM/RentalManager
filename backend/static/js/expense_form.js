(() => {
  const form = document.querySelector('[data-expense-form]');
  if (!form) return;
  const field = name => form.elements.namedItem(name);
  const panel = form.querySelector('[data-expense-ownership]');
  let serial = 0;
  function visibility() {
    const ownersBear = field('borne_by').value === 'owner';
    form.querySelector('[data-imputation-label]').hidden = !ownersBear;
    if (!ownersBear) field('imputation').value = 'property';
    const show = ownersBear && field('imputation').value === 'owner';
    form.querySelector('[data-specific-owner]').hidden = !show;
    field('owner_id').disabled = !show;
    field('owner_id').required = show;
  }
  async function loadOwnership() {
    const request = ++serial;
    const selected = field('owner_id').value || field('owner_id').dataset.selectedOwner;
    field('owner_id').replaceChildren(new Option('Seleccionar', ''));
    const property = field('property_id').value, date = field('expense_date').value;
    if (!property || !date) { panel.textContent = 'Seleccione finca y fecha para consultar la titularidad.'; return; }
    panel.textContent = 'Consultando titularidad…';
    try {
      const response = await fetch(`/expenses/ownership?${new URLSearchParams({property_id: property, expense_date: date})}`);
      if (!response.ok) throw new Error('ownership');
      const data = await response.json();
      if (request !== serial) return;
      panel.replaceChildren();
      panel.classList.toggle('alert-warning', Boolean(data.warning));
      panel.classList.toggle('alert', Boolean(data.warning));
      if (data.warning) panel.textContent = `${data.warning} Puede registrar el gasto ordinario; no podrá liquidarse hasta resolver el reparto.`;
      else {
        const title = document.createElement('strong'), list = document.createElement('ul');
        title.textContent = 'Propietarios en la fecha del gasto:';
        list.className = 'mb-0';
        for (const owner of data.owners) {
          const li = document.createElement('li');
          li.textContent = `${owner.name} · ${owner.percentage} %`;
          list.append(li);
          field('owner_id').add(new Option(owner.name, owner.id, false, String(owner.id) === selected));
        }
        panel.append(title,list);
      }
      delete field('owner_id').dataset.selectedOwner;
    } catch (error) {
      if (request === serial) panel.textContent = 'No se pudo consultar la titularidad. El gasto ordinario puede registrarse y revisarse después.';
    }
  }
  function proposeCategory() {
    const category = field('provider_id').selectedOptions[0]?.dataset.category;
    if (category && [...field('category_id').options].some(option => option.value === category)) field('category_id').value = category;
  }
  field('property_id').addEventListener('change', loadOwnership);
  field('expense_date').addEventListener('change', loadOwnership);
  field('imputation').addEventListener('change', visibility);
  field('borne_by').addEventListener('change', visibility);
  field('provider_id').addEventListener('change', proposeCategory);
  const quick = document.querySelector('[data-quick-provider]');
  quick.addEventListener('submit', async event => {
    event.preventDefault();
    const button = quick.querySelector('button[type="submit"],button.btn-primary');
    const error = quick.querySelector('[data-provider-error]');
    button.disabled = true; error.textContent = '';
    try {
      const response = await fetch('/providers/quick', {method:'POST',body:new FormData(quick)});
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'No se pudo crear el proveedor.');
      const option = new Option(data.name, data.id, true, true);
      option.dataset.category = data.category_id || '';
      field('provider_id').add(option); proposeCategory();
      bootstrap.Modal.getInstance(document.getElementById('newExpenseProvider')).hide();
      quick.reset(); field('provider_id').focus();
    } catch (failure) { error.textContent = failure.message; }
    finally { button.disabled = false; }
  });
  visibility(); loadOwnership();
  if (!field('category_id').value) proposeCategory();
})();
