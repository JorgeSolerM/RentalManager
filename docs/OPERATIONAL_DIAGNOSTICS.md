# Diagnóstico operativo — bloque 1

Estado 19/11/2026: implementado, validado y **activado en producción**.
No requiere migraciones. No activa geocodificación ni modifica conciliación iCal.
VERI*FACTU permanece fuera de este bloque.

### Activación completada — 19/11/2026, 01:03 CET

Administración: PID 18068. Web pública: PID 20036. HTTP local y HTTPS 200;
live/ready locales 200, diagnóstico desde Internet 404. Logs activos y privados,
sin descartes ni errores de escritura; cabecera de correlación comprobada.
Rotación configurada a 10 MiB y cinco copias; no se forzó volumen en producción.
Dashboard/editor renderizados con Actualizar ubicación; mapa con ocho fincas,
recursos JavaScript y datos del calendario accesibles. Regresión JavaScript: 19 passed.
Exportación existente: HTTP 200, text/calendar, VCALENDAR 2.0 válido, sin publicar token.
Quick_check ok y foreign_key_check limpio en BD y caché. Datos de negocio y caché
sin cambios; se excluyen de la huella las marcas operativas last_seen_in_feed_at
que puede actualizar el runner ordinario y la telemetría de room_calendars.
La lectura ICS actualiza la observación de exportación existente, no reservas.

iCal ya usaba el adaptador de diagnóstico: su definición XML se conservó intacta
en este despliegue. No se inició ni reinició su tarea. Último ciclo comprobado
00:55:55, resultado 0. Estado: 63 ok, 3 warning, 13 sin estado, 0 error.
Worker geográfico deshabilitado; ninguna consulta a Nominatim ni migración.

Manifiestos privados: 306 componentes administrativos y 283 públicos, más hash
de cada adaptador. Referencia Git 3c4926cd866b66cd8748b82a594e6158973dfc33;
en el momento del despliegue el delta operativo estaba sin commit, identificado
por hashes efectivos. El cierre Git no cambia esa referencia histórica ni requiere
reiniciar los procesos: los componentes se comparan por contenido.
Evidencia y backups definitivos: `data/runtime/operational-web-activation-20261119-r2/`.
El script de esa carpeta permite reversión por servicio con `-RollbackService admin`
o `-RollbackService public`, siempre con autorización/elevación. No modifica iCal.
No reutilizar para este fin el script del primer intento que incluía cambio de tarea iCal.

Incidencia durante esta activación: el primer smoke tenía mal codificada la palabra
«ubicación», causando un falso fallo. Se revirtió solo administración; se corrigió
el script privado de comprobación, sin cambiar la aplicación, y se repitió con nuevas
copias. El segundo intento finalizó correctamente. Se mantienen ambas evidencias.
Validación visual del usuario aprobada; cierre exclusivo del bloque autorizado.

Cierre del bloque: batería final consolidada 229 passed (Python), 19 passed
(JavaScript); un aviso de deprecación existente de Starlette/httpx. Diff sin errores,
componentes de diagnóstico del índice Git equivalentes a los instalados (normalizando
solo finales de línea). Manifiestos íntegros; archivos privados y output excluidos.
No se reinician servicios ni se ejecutan migraciones durante el cierre.

### Intento de activación y reversión — 19/11/2026

La activación autorizada superó health local, rechazo de diagnóstico por HTTPS,
render administrativo/público, logs sanitizados, exportación ICS e integridad.
Windows rechazó después actualizar la acción de la tarea iCal con «El nombre de
usuario o la contraseña no son correctos». La tarea usa logon Password.
Se revirtieron administración y web pública, con restauración de archivos
comprobada por SHA-256. Los nuevos endpoints vuelven a 404; diagnóstico desactivado.
PID finales de esa reversión: administración 3300, público 11408. HTTP local,
HTTPS y calendario vuelven a 200. El botón Actualizar ubicación se renderiza
tras la recarga del router de fincas existente, aunque el diagnóstico esté apagado.

La tarea iCal conserva `-m backend.cli.sync_calendars`; no se lanzó ni reinició.
Su ciclo ordinario de las 00:25 actualizó marcas last_seen_in_feed_at de cinco
reservas, manteniendo 74 registros. Durante la comprobación previa a ese ciclo,
todas las huellas de negocio coincidían con la referencia. El control posterior
detectó esa variación de bookings; no se han restaurado ni editado reservas.
Al terminar: 63 calendarios ok, 3 warning, 13 sin estado, 0 error. El timeout
HousingAnywhere presente antes del despliegue desapareció en el ciclo ordinario.

Copias, tareas exportadas y evidencia privada están en
`data/runtime/operational-activation-20261119/`. Los directorios privados de logs
se conservan para diagnóstico; los que existían recuperaron sus ACL anteriores.
Los nuevos mantienen acceso restringido. No hubo migraciones ni cambios de caché.
Antes de reintentar la activación de iCal hay que resolver con el usuario el
requisito de credenciales de Windows; no cambiar la identidad ni el tipo de logon
como alternativa. No afirmar que este intento dejó el diagnóstico desplegado.

## Registros persistentes

Activación explícita por proceso: `RM_DIAGNOSTICS_ENABLED=1`,
`RM_DIAGNOSTICS_LOG_DIR` absoluto y privado, `RM_RELEASE_COMMIT` con SHA completo.
Sin activación se mantiene el comportamiento previo. Directorios diferentes para
administración y web pública; opcionalmente otro para el CLI iCal.
No apuntar a carpetas montadas públicamente, compartidas con visitantes ni sincronizadas.

Cada línea UTF-8 es JSON: UTC, servicio, PID, instancia, commit de referencia,
código de evento. Las peticiones añaden identificador generado por el servidor,
método, plantilla de ruta, estado y duración. Inicio y final comparten identificador.
Las rutas no resueltas se reducen a un prefijo permitido o `/{unmatched}`.
No se guardan consultas, cuerpos, cookies, cabeceras, IP, URL de feeds,
mensajes de excepciones, parámetros SQL, nombres ni datos bancarios.
Los avisos de log existentes se convierten a categorías cerradas, sin copiar su texto.

Un escritor por proceso usa una cola limitada de 1.024 eventos. Rotación a 10 MiB,
cinco copias más archivo activo (aproximadamente 60 MiB por servicio).
Permisos denegados, disco lleno o cola llena no bloquean peticiones; pueden perderse
eventos. Se contabilizan pérdidas y errores. No redirigir stdout/stderr sin filtrar
a estos archivos: la consola de Uvicorn no tiene esta garantía de privacidad.
Un proceso abruptamente terminado puede perder la cola; no es auditoría contable.
No usar varios workers escribiendo el mismo archivo. La configuración actual es de
un worker por servicio. Un cambio futuro a múltiples procesos requiere revisar la rotación.

## Comprobaciones locales

Disponibles únicamente con la activación anterior:

- `/_ops/live`: proceso responde, sin consultar dependencias.
- `/_ops/ready`: lecturas SQLite de BD y caché geográfica cuando corresponde,
  siempre `mode=ro`, sin crear archivos. Espera de bloqueo SQLite 350 ms por archivo,
  presupuesto HTTP de un segundo y una única comprobación en vuelo por proceso.
  Resultado reutilizado un segundo. No consulta Nominatim ni servicios externos.
- `/_ops/logging`: activación, cola, eventos descartados y errores de escritura.
  Los errores son acumulados desde el arranque, incluso después de recuperarse.

Exigen cliente loopback y Host local, sin cabeceras de proxy. Desde el dominio
público devuelven 404, sin rutas internas ni detalles técnicos. GET/HEAD solamente.
Una llamada bloqueada en el sistema de archivos puede sobrevivir al presupuesto HTTP;
no se lanzan hilos adicionales indefinidos mientras esa comprobación siga pendiente.
Readiness comprueba lectura, no certifica integridad completa ni todas las tablas.

`python -m backend.cli.operational_status probe` contrasta liveness/readiness de
ambos puertos, catálogo local y HTTPS, con timeout de tres segundos por destino.
No sincroniza calendarios, no reinicia ni escribe datos. Hasta desplegar, los nuevos
endpoints pueden devolver 404: no significa que el servicio anterior esté caído.

Para investigar una caída: capturar hora UTC, PID/arranque/tarea, ejecutar probe,
consultar logging local y buscar `request_started` sin final por request_id.
Local correcto + HTTPS fallido orienta a proxy/túnel; live correcto + ready fallido,
a dependencias; ambos fallidos, a proceso/event loop/puerto. Son indicios, no una
causa raíz automática. No reiniciar antes de guardar evidencia ni volcar páginas privadas.

## Versiones y candidatos

`operational_status manifest --service admin|public --commit SHA --component
backend/ruta.py=RUTA_INSTALADA` genera JSON privado con SHA-256 de cada componente.
`verify-manifest ARCHIVO` comprueba si cambió alguno. No copia su contenido.
Los manifiestos contienen rutas físicas: conservarlos fuera de Git y de la web.
El commit es referencia; los hashes describen el conjunto real, que puede ser híbrido.
Un inventario de disco no prueba qué módulos cargó un proceso ya iniciado.

Preparación privada: `data/runtime/operational-preparation-20261119/` contiene
manifiestos independientes instalados/candidatos, adaptadores antes/candidatos,
variables por servicio y deltas de código. Es el material de preparación inicial;
los componentes instalados y verificados están identificados en la sección de
activación completada y en sus manifiestos independientes.
Los manifiestos candidatos deben regenerarse antes de desplegar si cambia el código.
Los deltas públicos no sustituyen íntegramente la aplicación por el checkout.

Administración utilizaba inicialmente cinco módulos congelados, ampliados en esta
activación con los componentes identificados por su manifiesto; el público utiliza
una copia aislada. Por ello no basta con reiniciar ni comparar HEAD. En la auditoría
inicial el calendario público coincidía con `3c4926cd866b66cd8748b82a594e6158973dfc33`,
mientras otros componentes públicos procedían de revisiones anteriores.

## Actualizar ubicación

Paquete administrativo: app_factory, routers properties/geolocation,
property_modal.html, properties.js, property-geolocation.js y diagnóstico core.
El contexto `manual_location_update_enabled` habilita el botón. El formulario
conserva CSRF, exige dirección guardada y reutiliza revisión/reintento existente.
El adaptador candidato actualiza los módulos congelados necesarios; no habilita
el worker. Durante el smoke no pulsar un reintento que llame al proveedor.

## iCal

Se añade un evento estructurado al resultado del runner existente, sin cambiar
selección, backoff, transacciones ni tratamiento de reservas desaparecidas.
Campos: identificador interno del calendario, resultado de lista cerrada y contadores
cancelled/disappeared/early_termination_conflicts, además de recibidos/creados/actualizados.
Permite diferenciar futuras advertencias que antes se reducían al estado warning.
No reconstruye retroactivamente el motivo de warnings anteriores.
El CLI lo activa mediante un adaptador privado con directorio propio y servicio
`ical`. La modificación autorizada de argumentos se verificó por comparación XML;
no cambió usuario, frecuencia, privilegios ni condiciones. No lanzar ciclos
extraordinarios para probarlo.

## Procedimiento de activación (para futuras operaciones autorizadas)

1. Revalidar SHA-256, diff y cuentas efectivas. Administración está configurada como
   1erPuesto; la tarea pública guardada como SYSTEM. Confirmar cuentas antes de ACL.
2. Exportar tareas y guardar copia de adaptadores y cada archivo destino antes de
   reemplazarlo. Registrar PID y versión. Conservar caché y BD, sin migrarlas.
3. Crear directorios privados separados, conceder únicamente los permisos necesarios
   al escritor correspondiente y cuentas de sistema/administración. Revisar ACL antes
   de aplicarlas. El cierre en Git no modifica permisos efectivos.
4. Instalar deltas y adaptadores, conservar variables privadas y worker=0. Preparar
   logging antes del import de la app si se desea capturar avisos de inicialización;
   los fallos anteriores al arranque de Python siguen requiriendo el Programador de tareas.
5. Reiniciar exclusivamente cada servicio autorizado, uno a uno. No tocar iCal.
6. Verificar live/ready/logging locales, rechazo público, HTTP y render Dashboard,
   editor de finca, catálogo/mapa/calendario, exportación ICS válida sin publicar URL,
   y logs privados sin secretos. Comprobar nuevos PID/manifiestos.
7. Registrar fecha de despliegue y revisión efectiva; no marcarlo desplegado antes.

## Reversión

Si falla una comprobación crítica, detener la activación. Restaurar adaptador,
configuración y archivos de **ese servicio** desde la copia previa, quitar la
activación de diagnóstico y reiniciar solo el servicio autorizado. Verificar HTTP
local/HTTPS y editor anterior. Restaurar ACL solo si se hubieran cambiado y existe
su copia. Conservar logs para investigar, privados; no borrar caché ni restaurar
BD, pues el bloque no modifica datos ni esquema.

## Validación y pendientes

Tests sintéticos: privacidad HTTP/excepciones, rotación, separación, disco/permisos,
cola limitada, correlación, health local/proxy, timeout/single-flight, SQLite solo
lectura, manifiestos y códigos iCal. Regresión Dashboard, mapa, geolocalización,
catálogo, calendario de colaboradores y runner/parser iCal; JavaScript correspondiente.
Validación previa al despliegue: batería consolidada 228 passed; revisión específica 19 passed
(solapada, no sumar); JavaScript 19 passed. Aviso existente de deprecación
Starlette/httpx. `git diff --check` correcto. BD real consultada únicamente en
lectura: quick_check ok, foreign_key_check sin filas; iCal 63 ok, 3 warning,
13 sin estado, 0 error. No sincronizaciones extraordinarias. La primera consulta
a la tarea programada devolvió acceso denegado; posteriormente se verificaron
cuentas y tareas con elevación. Los PID iniciales eran 14148 y 20136; los PID
posteriores y el smoke productivo constan en la activación completada.
Pendiente: observación de la rotación durante operación prolongada.
La diferencia Alembic código `a01729dbe348` / producción `b1283aedf459` se mantiene:
no se ha ejecutado migración ni stamp y este bloque no la necesita.
