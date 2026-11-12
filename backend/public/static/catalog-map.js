/* Local Leaflet assets load only after an explicit request to see the map. */
(function () {
  'use strict';
  const price = value => {
    const number = Number(value);
    return value != null && value !== '' && Number.isFinite(number) && number > 0
      ? new Intl.NumberFormat('es-ES', { maximumFractionDigits: 2 }).format(number) + ' €/mes'
      : 'Consultar precio';
  };
  if (typeof module !== 'undefined') module.exports = { price };
  if (typeof document === 'undefined') return;
  const dialog = document.querySelector('[data-catalog-map]');
  if (!dialog) return;
  const open = document.querySelector('[data-map-open]');
  const status = dialog.querySelector('[data-map-status]');
  const canvas = dialog.querySelector('[data-map-canvas]');
  const payload = JSON.parse(dialog.dataset.mapPayload);
  let map, assets, position, oldOverflow;
  function loadAssets() {
    if (assets) return assets;
    assets = Promise.all(['css', 'js'].map(type => new Promise((resolve, reject) => {
      const el = document.createElement(type === 'css' ? 'link' : 'script');
      if (type === 'css') { el.rel = 'stylesheet'; el.href = '/static/vendor/leaflet/leaflet.css'; }
      else el.src = '/static/vendor/leaflet/leaflet.js';
      el.onload = resolve; el.onerror = reject;
      document.head.append(el);
    })));
    return assets;
  }
  function element(tag, text, className) {
    const el = document.createElement(tag);
    if (text) el.textContent = text;
    if (className) el.className = className;
    return el;
  }
  function popup(property) {
    const root = element('div', '', 'map-popup');
    root.append(element('h3', property.name));
    property.rooms.forEach(room => {
      const row = element('div', '', 'map-room');
      if (room.image && room.image.startsWith('/')) {
        const img = element('img'); img.src = room.image; img.alt = ''; img.loading = 'lazy'; row.append(img);
      }
      const text = element('div');
      text.append(element('p', room.title), element('p', price(room.price)));
      const link = element('a', 'Ver habitación'); link.href = '/habitaciones/' + encodeURIComponent(room.slug);
      link.setAttribute('aria-label', 'Ver habitación: ' + room.title);
      text.append(link); row.append(text); root.append(row);
    });
    return root;
  }
  open.addEventListener('click', async () => {
    position = window.scrollY; oldOverflow = document.body.style.overflow;
    dialog.showModal(); document.body.style.overflow = 'hidden';
    if (!payload.properties.length) {
      status.textContent = 'No hay habitaciones que cumplan estos filtros con ubicación verificada. Puedes consultar todas las opciones en el catálogo.';
      canvas.hidden = true; return;
    }
    status.textContent = payload.omitted ? 'Algunas habitaciones no se muestran porque su ubicación aún no está verificada.' : '';
    try {
      await loadAssets();
      if (!dialog.open) return;
      if (!map) {
        map = L.map(canvas, { scrollWheelZoom: true });
        L.tileLayer(payload.tiles, { maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>' }).on('tileerror', () => {
          status.textContent = 'La cartografía no está disponible temporalmente. Puedes seguir consultando las habitaciones en el catálogo.';
        }).addTo(map);
        const bounds = [];
        payload.properties.forEach(property => {
          const point = [property.latitude, property.longitude]; bounds.push(point);
          L.marker(point, { title: property.name, alt: property.name, icon: L.divIcon({ className: 'map-pin', html: String(property.rooms.length), iconSize: [40,40] }) })
            .addTo(map).bindPopup(popup(property), { maxWidth: 270 });
        });
        map.fitBounds(bounds, { padding: [35,35], maxZoom: 16 });
      }
      map.invalidateSize();
    } catch (_) {
      status.textContent = 'No se ha podido cargar el mapa. Las habitaciones siguen disponibles en el catálogo.';
    }
  });
  dialog.querySelector('[data-map-close]').addEventListener('click', () => dialog.close());
  dialog.addEventListener('close', () => {
    document.body.style.overflow = oldOverflow;
    open.focus({ preventScroll: true }); window.scrollTo(0, position);
  });
})();
