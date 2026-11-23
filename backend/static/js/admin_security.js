/* Host-only CSRF transport. Never forward the token to another origin. */
(() => {
  'use strict';
  const meta = document.querySelector('meta[name="rm-admin-csrf"]');
  if (!meta || !meta.content) return;
  const token = meta.content;
  const remote = document.querySelector('meta[name="rm-admin-remote"]')?.content === '1';
  const safe = method => ['GET', 'HEAD', 'OPTIONS'].includes(method.toUpperCase());
  const sameOrigin = url => new URL(url, location.href).origin === location.origin;
  const formToken = form => {
    if (safe(form.method || 'GET') || !sameOrigin(form.action || location.href)) return;
    let input = form.querySelector('input[name="_rm_csrf"]');
    if (!input) { input = document.createElement('input'); input.type = 'hidden'; input.name = '_rm_csrf'; form.appendChild(input); }
    input.value = token;
  };
  const originalFetch = window.fetch;
  window.fetch = function(input, init) {
    const request = new Request(input, init);
    if (sameOrigin(request.url) && !safe(request.method)) {
      const headers = new Headers(request.headers); headers.set('X-RM-CSRF', token);
      return originalFetch.call(this, new Request(request, {headers}));
    }
    return originalFetch.call(this, request);
  };
  const open = XMLHttpRequest.prototype.open, send = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function(method, url, ...rest) {
    this.rmCsrfRequired = sameOrigin(url) && !safe(method);
    return open.call(this, method, url, ...rest);
  };
  XMLHttpRequest.prototype.send = function(...args) {
    if (this.rmCsrfRequired) this.setRequestHeader('X-RM-CSRF', token);
    return send.apply(this, args);
  };
  document.addEventListener('submit', event => formToken(event.target), true);
  const submit = HTMLFormElement.prototype.submit;
  HTMLFormElement.prototype.submit = function() { formToken(this); return submit.call(this); };
  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('form').forEach(formToken);
    if (remote) {
      const notice = document.createElement('div'); notice.className = 'alert alert-info m-2';
      notice.setAttribute('role', 'status');
      notice.textContent = 'Acceso remoto de consulta. No se permiten modificaciones ni operaciones económicas.';
      document.body.prepend(notice);
    }
  });
})();
