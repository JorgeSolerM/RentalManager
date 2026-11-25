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
    // Named controls such as <select name=method> shadow form.method/action.
    const method = form.getAttribute('method') || 'GET';
    const action = form.getAttribute('action') || location.href;
    if (safe(method) || !sameOrigin(action)) return;
    let input = form.querySelector('input[name="_rm_csrf"]');
    if (!input) { input = document.createElement('input'); input.type = 'hidden'; input.name = '_rm_csrf'; form.appendChild(input); }
    input.value = token;
  };
  const csrfFailure = () => {
    if (document.getElementById('rm-csrf-error')) return;
    const alert = document.createElement('div');
    alert.id = 'rm-csrf-error'; alert.className = 'alert alert-danger m-2';
    alert.setAttribute('role', 'alert'); alert.tabIndex = -1;
    alert.textContent = 'No se ha guardado el formulario: ha caducado o no es válido. Conserva los datos que necesites y recarga la página antes de volver a enviarlo.';
    (document.querySelector('main') || document.body).prepend(alert);
    alert.focus();
  };
  const checkResponse = async response => {
    if (response.status === 403 && sameOrigin(response.url) &&
        response.headers.get('content-type')?.includes('application/json')) {
      try { if ((await response.clone().json()).code === 'csrf_denied') csrfFailure(); } catch (_) {}
    }
    return response;
  };
  const originalFetch = window.fetch;
  window.fetch = function(input, init) {
    const request = new Request(input, init);
    if (sameOrigin(request.url) && !safe(request.method)) {
      const headers = new Headers(request.headers); headers.set('X-RM-CSRF', token);
      return originalFetch.call(this, new Request(request, {headers})).then(checkResponse);
    }
    return originalFetch.call(this, request).then(checkResponse);
  };
  const open = XMLHttpRequest.prototype.open, send = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function(method, url, ...rest) {
    this.rmCsrfRequired = sameOrigin(url) && !safe(method);
    if (!this.rmCsrfListenerInstalled) {
      this.rmCsrfListenerInstalled = true;
      this.addEventListener('load', () => {
        if (this.status !== 403 || !sameOrigin(this.responseURL) ||
            !this.getResponseHeader('content-type')?.includes('application/json')) return;
        try {
          const body = this.responseType === 'json' ? this.response :
            (!this.responseType || this.responseType === 'text' ? JSON.parse(this.responseText) : null);
          if (body?.code === 'csrf_denied') csrfFailure();
        } catch (_) {}
      });
    }
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

  });
})();
