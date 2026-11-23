# Administración remota: protecciones desplegadas, acceso remoto desactivado

## Alcance y estado

Protecciones desplegadas en administración el 23/11/2026, tras pruebas aisladas.
El acceso remoto continúa desactivado. No se ha cambiado DNS, Cloudflare,
tareas de Windows, firewall ni el túnel. No hay migración.
Subfase económica 4.3 y VERI*FACTU permanecen fuera de este bloque.

Los ocho componentes de ejecución coinciden con el candidato probado. Se cargan
las dependencias criptográficas desde un directorio privado de administración.
El arranque actual de la tarea se conserva: antes de activar Access habrá que
configurar `--no-proxy-headers`. El adaptador privado desactiva el access log bruto
de Uvicorn y conserva el registro JSON sanitizado. No se ha habilitado ningún
hostname administrativo externo.

El cierre se valida también sobre HEAD más los 15 archivos de este bloque, sin
incorporar la reutilización de inquilinos. La prueba de búsquedas POST siempre
verifica la capacidad de consulta y prueba además el handler real cuando esté
presente; ese handler pertenece al checkpoint independiente de inquilinos.

Validación de cierre: 91 pruebas Python y una prueba de navegador superadas sobre
HEAD más los archivos de seguridad, con bases sintéticas y sin el desarrollo
pendiente de inquilinos. Se verifican JWT, hostnames, CSRF, permisos de consulta,
compatibilidad iCal y diagnóstico. Los ocho hashes de ejecución coinciden con
los instalados. La ruta iCal productiva se comprueba con un token ficticio; los
ICS válidos se prueban en aislamiento, sin consultar tokens productivos.

La administración local conserva las operaciones existentes. Los POST/PUT/PATCH/
DELETE necesitan ahora el token CSRF que entrega la página y envía el adaptador
de formularios/fetch/XHR. Scripts locales que escriban deberán obtener ese token;
no hay una excepción basada en User-Agent ni en la ausencia de Origin.

La modalidad remota está deshabilitada por defecto; no existe modalidad remota
de escritura. El hostname remoto, incluso configurado, no se acepta si falta la
activación. Los hostnames locales autorizados son localhost, 127.0.0.1 y ::1,
con conexión efectiva loopback y sin cabeceras de reenvío/identidad remota.

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

## Configuración privada pendiente

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

Requisito del futuro arranque: `--host 127.0.0.1 --port 8000 --no-proxy-headers
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
no-referrer, Permissions-Policy restrictiva y CSP. HSTS solo en el hostname remoto.
CSP conserva unsafe-inline por compatibilidad con plantillas existentes y permite
Bootstrap en cdn.jsdelivr.net; no equivale a una política estricta basada en nonces.
Los errores inesperados remotos no muestran detalles y llevan caché privada.

Eventos admin_access en el sink JSON existente, con rotación ya establecida:
código cerrado de resultado, método, estado y ruta normalizada. No se registran
tokens, cookies, cabeceras, cuerpos, querystrings, correos ni IPs. El fallo de log
no bloquea la aplicación. Desactivar el access log bruto de Uvicorn evita que otro
canal registre consultas sensibles. Un diagnóstico desactivado implica que estos
eventos no persisten: comprobar logging antes de habilitar remoto.

## Activación futura (requiere autorización)

1. Comparar hashes del manifiesto con código desplegado y overlays privados del
   adaptador administrativo. Integrar la instalación de seguridad en la fábrica
   realmente cargada; no sobrescribir a ciegas los overlays de diagnóstico.
2. Respaldar esos archivos, configuración y tarea administrativa. Ninguna migración.
3. Instalar dependencias en un entorno candidato, probarlo y solo después preparar
   su inclusión en el entorno de administración. No instalar paquetes en caliente
   en el entorno compartido por servicios en ejecución.
4. Instalar componentes, conservar remote_enabled=0, adaptar únicamente el arranque
   administrativo a los flags anteriores y comprobar acceso local y CSRF.
5. En una fase autorizada separada, revisar zona/túnel completo; crear Access para
   el hostname administrativo con identidad exacta y MFA, sin Bypass. Configurar
   Protect with Access en cloudflared antes de publicar la ruta.
6. Configurar issuer/audiencia/identidades; activar remoto solo después de verificar
   políticas. No abrir puertos, alterar iCal ni reiniciar el conector compartido
   innecesariamente. Validar en Android sobre datos móviles.
7. Comprobar sesiones revocadas, bypass por otros hostnames, origin/JWT inválidos,
   writes denegados, consultas POST, caché, cookies, logs y regresión pública/iCal.

## Reversión

Primero bloquear Access/revocar sesiones y retirar únicamente la ruta remota de
administración. No eliminar Access dejando el origen publicado. Establecer
RM_ADMIN_REMOTE_ENABLED=0 y recargar exclusivamente administración cuando se
autorice. Si es necesario, restaurar componentes/launcher/tarea administrativos
respaldados. No detener cloudflared compartido, no tocar la BD ni los servicios
públicos/iCal. Confirmar acceso local y ausencia de acceso remoto antes de cerrar.

## Límites conocidos

- No se ha configurado ni probado el tenant real de Cloudflare, MFA, sesión Access,
  TLS real del futuro subdominio, revocación real ni navegación Android remota.
- La aplicación rechaza remoto por defecto; no se ha publicado ningún hostname.
- Primera fase solo consulta: algunas acciones de edición existentes siguen
  visibles y muestran un rechazo explícito al intentar ejecutarlas.
- El rediseño móvil y una CSP estricta con nonces son trabajos separados.
- Formulario mutador sin cabecera CSRF: límite de lectura para inspección de 32 MiB.
- La lista de capacidades debe revisarse ante nuevas rutas o nuevos efectos en GET.
- Versiones de tests y resultados exactos se entregan en VALIDATION.md del candidato.
