# Administración remota: operación en solo lectura

## Estado al 25/11/2026

La administración remota está operativa con Google y TOTP, exclusivamente en
`read_only`. El usuario ha confirmado la navegación remota y la creación local
de reservas tras la reparación CSRF. Esta confirmación funcional no sustituye
las pruebas automatizadas de rechazo de escrituras y de identidad inválida.

Código de seguridad: commit `f354fe4151589204b6b924a18f8c9ad498f0f1a0`.
Reparación CSRF y pruebas: commit `b2733894ab65d922d8382cfa6b4ca40ad7dd62b4`.
La activación modifica configuración privada de ejecución, no añade secretos al
repositorio. La tarea administrativa utiliza `--no-proxy-headers` y
`--no-access-log`, con escucha exclusiva en loopback. No existe modo remoto de
escritura. La administración local conserva sus operaciones con CSRF.

La reparación conserva Origin estricto y la cookie firmada: cambia la política
Referrer-Policy a `same-origin`, evita propiedades DOM ocultadas por controles
llamados method/action y presenta errores CSRF navegables para formularios HTML.
Las respuestas API conservan el error JSON; fetch/XHR muestran un aviso accesible.

El cierre no modifica el túnel, Cloudflare, datos reales, web pública ni iCal;
no ejecuta migraciones ni reinicia servicios. La reutilización de inquilinos,
el candidato económico, output/ y la subfase económica 4.3 quedan separados.

## Validación de cierre del 25/11/2026

- Copia limpia de `b273389`: 165 pruebas Python superadas y un fallo previo de
  conteo de consultas de habitaciones (cuatro frente a tres). Incluye las 76
  pruebas de seguridad remota/CSRF y pruebas de reservas, personas, habitaciones,
  fincas, propietarios, configuración, cobros, gastos y pagos a propietarios.
- Edge headless: una prueba superada con envíos efectivos de formularios, submit
  programático, fetch y XHR; transporte de CSRF limitado al origen propio.
- Copia aislada con los cambios pendientes de reservas/inquilinos: 31 pruebas
  superadas y tres fallos de expectativa de cabecera. El endpoint responde 200
  con `Cache-Control: private, no-store`; las pruebas pendientes esperan la
  cadena exacta `no-store`. Se conservan sin modificar ni incluir en este commit.
- Los ocho archivos de fábrica, seguridad, registro, JavaScript y plantilla
  desplegados coinciden con HEAD al normalizar finales de línea. Se comparó el
  mapa real del launcher privado; no se afirma identidad de todo el despliegue,
  que conserva overlays y cambios pendientes ajenos a este cierre.
- Se comprobó en modo lectura la tarea administrativa: loopback puerto 8000,
  `--no-proxy-headers --no-access-log`. La configuración privada está activada
  exclusivamente en `read_only`.

Todas las bases de estas pruebas son sintéticas y aisladas. No se ejecutaron
migraciones ni operaciones sobre datos productivos. La batería general no está
completamente verde por los fallos indicados; no se ocultaron ni debilitaron
aserciones para cerrar el bloque. Los registros detallados y la comparación de
archivos permanecen en el directorio privado de evidencias del cierre.

## Arquitectura

Android → HTTPS → Access con MFA → cloudflared con Protect with Access →
administración loopback → validación JWT → capacidades de consulta → SQLite
query_only para la dependencia administrativa. No se cambian las reglas económicas.

El middleware es exclusivo de create_app administrativo. La aplicación pública
mantiene su propia fábrica. calendarios.hsi-rents.com conserva exclusivamente
GET/HEAD del patrón `/ical/rooms/{token}/{platform}.ics`, incluida su caché y ETag.
El hostname administrativo remoto no permite exportar iCal. No se amplía ninguna
ruta pública ni se aceptan rutas administrativas en el hostname de calendarios.

La autorización remota utiliza una lista positiva en admin_read_policy.py:
Dashboard, Gantt/datos, fincas, habitaciones, personas, propietarios, gastos,
liquidaciones, documentos ya generados, reservas y cuenta económica. Único POST:
`/bookings/person-search`, consulta revisada que también exige CSRF. Generación
de documentos, previews económicos, edición, sincronización, facturación,
configuración, docs, OpenAPI, diagnósticos y websockets quedan denegados. Nuevas
rutas quedan bloqueadas hasta revisión. El servidor es la autoridad; los botones
existentes pueden seguir visibles, pero no ejecutan escrituras remotamente.

SQLite query_only actúa como segunda barrera en la conexión remota, fijada durante
toda la sesión y restaurada antes de devolverla al pool. Si la restauración falla,
la conexión se invalida. No se cambian el fichero DB ni sus permisos.

## Identidad y claves

PyJWT con cryptography valida RS256 exclusivamente, firma RSA >=2048, kid, issuer,
audience, exp, iat, sub y email; nbf se valida si existe. Solo identidades explícitas.
La cabecera de correo sin firma no concede identidad. Tampoco se admite autenticar
únicamente por la cookie CF_Authorization. La identidad verificada está en
request.state.admin_identity, no se persiste ni se registra su correo.

Las claves públicas se obtienen únicamente desde el emisor configurado:
`https://<equipo>.cloudflareaccess.com/cdn-cgi/access/certs`.
No se siguen URLs del token ni redirecciones. Timeout 3 s, respuesta <=64 KiB,
caché en memoria 5 minutos, refresh serializado y limitado a una vez cada 30 s.
Un kid desconocido provoca refresh limitado; sin clave vigente verificable se
rechaza el acceso. No se utilizan claves caducadas indefinidamente ante una caída.
Las pruebas generan claves sintéticas en memoria y simulan todas las respuestas.

Referencias: https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/authorization-cookie/validating-json/
y https://pyjwt.readthedocs.io/en/stable/usage.html

## Configuración privada de ejecución

Configurar solo en el adaptador privado, nunca versionar valores de producción:

| Variable | Valor/función |
|---|---|
| RM_ADMIN_REMOTE_ENABLED | `0` por defecto; `1` únicamente tras configurar y probar Access |
| RM_ADMIN_REMOTE_HOST | hostname administrativo independiente, sin esquema ni puerto |
| RM_ADMIN_ACCESS_ISSUER | origen HTTPS del equipo cloudflareaccess.com, sin path |
| RM_ADMIN_ACCESS_AUDIENCE | audiencia exacta de la aplicación Access |
| RM_ADMIN_ACCESS_IDENTITIES | identidades exactas autorizadas, separadas por comas |
| RM_ADMIN_REMOTE_MODE | exclusivamente `read_only` |
| RM_DIAGNOSTICS_ENABLED | `1` para persistir también accesos y rechazos |
| RM_DIAGNOSTICS_LOG_DIR | directorio privado absoluto ya preparado para administración |

Las claves públicas se descubren desde el issuer; no se configura una URL JWKS
arbitraria ni una clave privada. No se requiere secreto de Cloudflare en la app.
CSRF usa un secreto aleatorio por proceso, no almacenado en Git. Las páginas
abiertas antes de reiniciar necesitarán recargarse. Para este despliegue se mantiene
un solo proceso Uvicorn: múltiples workers requerirían coordinar el secreto CSRF.

## Proxy, cookies, cabeceras y registros

Arranque administrativo requerido: `--host 127.0.0.1 --port 8000 --no-proxy-headers
--no-access-log`. No usar procesamiento previo de X-Forwarded-For de Uvicorn:
la aplicación necesita ver el peer real loopback y valida el JWT antes de aceptar
el esquema HTTPS. X-Forwarded-Proto debe ser único y exactamente https; Forwarded
se rechaza y X-Forwarded-Host, si existe, debe coincidir. Se descartan cabeceras
de identidad/proxy antes del handler. Ninguna IP reenviada concede acceso local.

El token CSRF está firmado y vinculado al origen exacto, caduca en dos horas y
requiere cookie y valor concordantes. Cookie local HttpOnly/SameSite=Strict,
host-only; en remoto prefijo __Host-, Secure, HttpOnly, SameSite=Strict, Path=/,
sin Domain. Los POST rechazan Origin diferente o null y Fetch Metadata cross-site
o same-site. La cookie de Access pertenece a Cloudflare: revisar sus atributos
en la activación real; no convertirla en una cookie compartida con la web pública.

Respuestas administrativas privadas no-store/no-cache, noindex, nosniff, DENY,
same-origin (Referrer-Policy), Permissions-Policy restrictiva y CSP. HSTS solo en el hostname remoto.
CSP conserva unsafe-inline por compatibilidad con plantillas existentes y permite
Bootstrap en cdn.jsdelivr.net; no equivale a una política estricta basada en nonces.
Los errores inesperados remotos no muestran detalles y llevan caché privada.

Eventos admin_access en el sink JSON existente, con rotación ya establecida:
código cerrado de resultado, método, estado y ruta normalizada. No se registran
tokens, cookies, cabeceras, cuerpos, querystrings, correos ni IPs. El fallo de log
no bloquea la aplicación. Desactivar el access log bruto de Uvicorn evita que otro
canal registre consultas sensibles. Un diagnóstico desactivado implica que estos
eventos no persisten: comprobar logging antes de habilitar remoto.

## Configuración de Cloudflare comprobada

La aplicación self-hosted cubre únicamente el hostname administrativo. Su política
Allow limita la identidad a la cuenta autorizada y exige Google. La aplicación
acepta solo ese proveedor; no se utiliza Bypass ni autenticación automática del
cliente Cloudflare One. La sesión de aplicación y política dura una hora.

MFA independiente está personalizado tanto en aplicación como en política:
aplicación autenticadora (TOTP), duración de una hora. La ruta administrativa del
túnel apunta al servicio loopback y tiene Protect with Access activo, con equipo
y AUD correspondientes a la aplicación. Los valores concretos de equipo, AUD,
identidad y configuración de ejecución se conservan fuera de Git.

Rutas de consulta del panel (no requieren cambiar ni guardar configuración):

- Zero Trust → Access controls → Applications → aplicación administrativa → Edit
  → Application details → Authentication → Identity / MFA.
- Zero Trust → Access controls → Policies → política administrativa → Edit:
  identidad, proveedor, duración y MFA independiente.
- Networking → Tunnels → túnel existente → Routes → hostname administrativo
  → Edit → Additional application settings → Access: Protect with Access,
  Team name y Application Audience (AUD).

La comprobación manual solicitó Google y TOTP. Durante la prueba de revocación
se observó una nueva cadena de redirecciones por Access. No se ha realizado una
prueba independiente de reproducción del JWT anterior: no se afirma que la
validación criptográfica local consulte por sí sola una lista de revocación.
El origen valida firma, vigencia, emisor, audiencia e identidad; Access controla
las sesiones en el borde. Un nuevo inicio de sesión autorizado sigue permitido.

## Desactivación del acceso remoto (procedimiento, no ejecutado en el cierre)

1. Respaldar el launcher privado **actual**, su mapa de módulos y la definición
   de la tarea «RentalManager - Servidor», en almacenamiento privado. Registrar
   hashes y fecha. No copiar secretos a Git ni a registros públicos.
2. En el launcher administrativo vigente, cambiar únicamente
   `RM_ADMIN_REMOTE_ENABLED` a `0`. Conservar el modo `read_only`, las protecciones
   CSRF, JWT y el resto de configuración. No restaurar una versión anterior a la
   reparación CSRF ni reemplazar otros overlays a ciegas.
3. Cuando se autorice la intervención, reiniciar exclusivamente
   «RentalManager - Servidor» para que el proceso lea el cambio. No reiniciar
   Cloudflared ni la web pública, abrir puertos, modificar DNS o rutas iCal.
4. Comprobar que la administración local carga y que el hostname remoto devuelve
   `remote_disabled` después de Access. Sin sesión puede verse antes el login de
   Cloudflare: eso por sí solo no demuestra que el origen esté desactivado.
5. Conservar Access y Protect with Access. Si además se necesita revocar sesiones,
   hacerlo como acción separada autorizada en Zero Trust → Team & Resources →
   Users → usuario → Revoke sessions. La revocación no sustituye el paso 2:
   una identidad autorizada podría iniciar una nueva sesión.

Para revertir una desactivación, comparar el respaldo con la versión actual,
verificar de nuevo identidad/MFA/AUD y restaurar solo el indicador de activación,
con autorización y reinicio exclusivo administrativo. Mantener siempre
`read_only`. Los respaldos y scripts del despliegue son privados; verificar sus
hashes y alcance antes de utilizarlos, pues un respaldo antiguo puede revertir
correcciones posteriores. No tocar base de datos ni migraciones.

## Límites conocidos

- Primera fase solo consulta: algunas acciones de edición siguen visibles y
  muestran un rechazo explícito al intentar ejecutarlas.
- La confirmación de navegación real procede del usuario. Las escrituras con
  identidad válida se prueban en aislamiento, no sobre datos productivos.
- La revocación observada no equivale a una prueba independiente de replay de JWT.
- El rediseño móvil y una CSP estricta con nonces son trabajos separados.
- Formulario mutador sin cabecera CSRF: lectura de inspección limitada a 32 MiB.
- Revisar capacidades ante nuevas rutas o nuevos efectos secundarios en GET.
- Existe un fallo previo de conteo de consultas de habitaciones (espera tres,
  observa cuatro), reproducido también sin la reparación CSRF. No se cambia
  esa aserción ni se presenta la batería general como totalmente verde.
