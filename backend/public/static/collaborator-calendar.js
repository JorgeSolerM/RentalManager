/* Read-only: no booking endpoints, storage, analytics or mutation handlers. */
(() => {
  'use strict';
  const status = document.getElementById('calendar-status');
  const region = document.getElementById('calendar-scroll');
  const period = document.getElementById('calendar-period');
  const dayLabel = value => new Intl.DateTimeFormat('es-ES', {timeZone:'UTC'}).format(new Date(value+'T12:00:00Z'));
  const element = (tag, text, cls) => {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (cls) node.className = cls;
    return node;
  };
  function clear(message) {
    region.replaceChildren(); region.hidden = true; period.textContent = ''; status.textContent = message;
  }
  function render(data) {
    const dates = [];
    for (let d = new Date(data.start+'T12:00:00Z'); d.toISOString().slice(0,10)<data.end; d.setUTCDate(d.getUTCDate()+1)) {
      dates.push(d.toISOString().slice(0,10));
    }
    const table = element('table', undefined, 'availability-table');
    const caption = element('caption', 'Disponibilidad diaria por finca y habitación'); table.append(caption);
    const head = element('thead'), months = element('tr'), days = element('tr');
    const label = element('th', 'Finca / habitación', 'calendar-label'); label.rowSpan=2; label.scope='col'; months.append(label);
    const monthGroups = [];
    for (const value of dates) {
      const key=value.slice(0,7), last=monthGroups[monthGroups.length-1];
      if (last && last.key===key) last.count++; else monthGroups.push({key,count:1,date:value});
      const cell=element('th', String(Number(value.slice(8))), 'day'); cell.scope='col'; cell.title=dayLabel(value); days.append(cell);
    }
    for (const group of monthGroups) {
      const cell=element('th', new Intl.DateTimeFormat('es-ES',{month:'long',year:'numeric',timeZone:'UTC'}).format(new Date(group.date+'T12:00:00Z')));
      cell.colSpan=group.count; cell.scope='colgroup'; months.append(cell);
    }
    head.append(months,days); table.append(head);
    let count=0;
    for (const property of data.properties) {
      const body=element('tbody'), divider=element('tr',undefined,'property-divider');
      const groupName=element('th',property.name,'calendar-label'); groupName.scope='rowgroup';
      const filler=element('th',''); filler.colSpan=dates.length; divider.append(groupName,filler); body.append(divider);
      for (const room of property.rooms) {
        count++; const row=element('tr'), identity=element('th',undefined,'calendar-label'); identity.scope='row';
        const link=element('a',property.name); link.href=room.listing_url; link.target='_blank'; link.rel='noopener noreferrer'; link.referrerPolicy='no-referrer';
        link.title='Ver anuncio de esta habitación'; link.setAttribute('aria-label',property.name+' · '+room.name+' · Ver anuncio de esta habitación');
        identity.append(link,element('strong',room.name),element('small','Disponible desde '+dayLabel(room.available_from))); row.append(identity);
        for (const date of dates) {
          const occupied=room.occupied.some(interval => interval.start<=date && date<interval.end);
          const kind=occupied?'occupied':date>=room.available_from?'available':'gap';
          const text={occupied:'Ocupado',available:'Disponible',gap:'Hueco previo: no se ofrece'}[kind];
          const cell=element('td',{occupied:'×',available:'✓',gap:'·'}[kind],kind+' day');
          cell.setAttribute('aria-label',dayLabel(date)+': '+text); cell.title=dayLabel(date)+': '+text; row.append(cell);
        }
        body.append(row);
      }
      table.append(body);
    }
    const left=region.scrollLeft, top=region.scrollTop;
    region.replaceChildren(table); region.hidden=count===0; region.scrollLeft=left; region.scrollTop=top;
    period.textContent=dayLabel(data.start)+' — '+dayLabel(data.last_day)+' · Europe/Madrid';
    status.textContent=count?count+' habitaciones · Consulta actualizada':'No hay habitaciones con disponibilidad definitiva en estos seis meses.';
  }
  async function refresh() {
    const token = location.hash.slice(1);
    if (!/^[A-Za-z0-9_-]{43}$/.test(token)) { clear('Enlace no válido o incompleto. Solicita un enlace de acceso.'); return; }
    try {
      const response=await fetch('/colaboradores/disponibilidad/data',{method:'GET',cache:'no-store',credentials:'omit',referrerPolicy:'no-referrer',headers:{Authorization:'Bearer '+token}});
      if (!response.ok) { clear('Acceso no disponible. El enlace puede haber sido revocado.'); return; }
      render(await response.json());
    } catch (_) { clear('No se pudo actualizar la disponibilidad. Vuelve a abrir el enlace.'); }
  }
  refresh();
  window.addEventListener('hashchange', refresh);
  setInterval(refresh,60000);
})();
