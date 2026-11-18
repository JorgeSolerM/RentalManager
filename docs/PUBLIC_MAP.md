# Mapa del catálogo público

## Variantes y revisión administrativa

Actualización manual desde Fincas: el editor de una finca existente incluye
«Actualizar ubicación», incluso sin incidencias abiertas. Consulta la pantalla
de revisión para obtener el formulario protegido y envía el mismo POST de
reintento; no introduce una segunda implementación del geocodificador.
Si calle, número o municipio tienen cambios sin guardar, pide guardarlos y
reabrir el editor primero. El resultado se muestra en la pantalla de revisión.
Esta nueva entrada desde el editor está pendiente de despliegue.

Cambiar nombre administrativo, nombre público, planta o puerta no cambia la
clave geográfica del edificio. Calle, número y municipio sí la cambian tras su
normalización: la coordenada antigua deja de usarse hasta verificar la nueva.
El mapa obtiene el nombre público actual de la BD, no de la caché geográfica.
La actualización se observa al volver a cargar el catálogo; un mapa ya abierto
conserva los datos de la página que cargó. No se ejecutan consultas al guardar.

El código incorpora `/properties/{id}/geolocation` exclusivamente en
administración. «Revisar» abre esta pantalla, no la respuesta JSON de la finca.
Muestra dirección, estado, motivo, último intento, variante y hasta veinte intentos.
Reutiliza el modal y el servicio existente de fincas para editar; el guardado vuelve
a la revisión. Google Maps es un enlace de búsqueda, sin API ni coordenadas manuales.

Las acciones exigen acceso local, Host local, formulario firmado con caducidad,
cookie HttpOnly/SameSite y comprobación de origen. La firma se vincula a la dirección:
si cambia en otra ventana hay que recargar. La aplicación pública no registra estas
rutas. El botón queda deshabilitado por defecto: requiere
`PUBLIC_GEOCODING_ADMIN_RETRY_ENABLED=1` y un User-Agent identificativo.
No se eleva Windows desde una petición HTTP ni se cambian ACL automáticamente.

CLI, worker opcional y reintento usan la misma búsqueda progresiva: original,
tipo de vía castellano y tipo de vía valenciano/localidad Elx. Las denominaciones
propias no se traducen libremente. Gerona/Girona se consulta como candidata, pero
NO se acepta como equivalencia demostrada. El callejero puede contener ambas vías.
Para una equivalencia comprobada se admite un archivo privado configurado mediante
`PUBLIC_GEOCODING_ALIASES`, con una lista de objetos `city`, `original`, `translated`
y `evidence`. La evidencia debe comprobarse por un responsable antes de incorporarla;
rellenar el campo no verifica por sí mismo una equivalencia. No se ha configurado
un alias general Gerona/Girona. La ubicación concreta de Gerona 5 fue confirmada
por el titular y conservada en la caché privada; esto no autoriza equivalencias
para otras direcciones. Pruebas usan únicamente equivalencias sintéticas.

Se conservan las claves y las ocho columnas de `locations`, compatibles con el
lector desplegado. Dos tablas adicionales **solo en la caché**, `geocoding_queries`
y `geocoding_attempts`, conservan variantes, estado, HTTP, motivo y fechas.
No hay migración Alembic ni cambios en la BD de negocio. Los diagnósticos antiguos
sin variante se muestran como no conservados; no se inventa un historial.

Los aciertos se reutilizan sin HTTP. Los fallos de red activan pausa global de
24 horas; separación mínima de 16 segundos y bloqueo SQLite compartido. Una reserva
persistente del proveedor evita consultas inmediatas si el proceso se interrumpe.
Un reintento manual no repite la misma variante antes de 24 horas ni supera tres
intentos por variante. La ambigüedad detiene las alternativas: no se escoge un punto
por descarte. Se mantiene el límite previo de errores agotados en la caché antigua.

Estado de entrega: revisión y variantes desplegadas de forma controlada el
18/11/2026, con reintentos habilitados y permisos de caché para administración.
El worker sigue apagado. La validación manual fue aprobada por el usuario.
El acceso adicional «Actualizar ubicación» desde el editor se incorpora a este
checkpoint, pero no se despliega durante su cierre. La previsualización utiliza
una BD y un proveedor simulado independientes. VERI*FACTU no forma parte de este bloque.

Validación de este bloque: batería consolidada Python de geolocalización, Dashboard,
reservas, iCal y web pública: 168 passed; JavaScript de mapa/editor: 7 passed.
Tras los últimos casos de caché, se repite la batería unitaria específica (resultados
solapados, no sumar). Los tests usan MockTransport, nunca Nominatim real.
La previsualización HTTP sintética funciona; el controlador visual devolvió
«Acceso denegado», por lo que no se afirma validación visual ni de consola real.

Revalidación del 18/11/2026: 113 tests de geocodificación, incidencias, rutas de
revisión, integración pública, disponibilidad y calendarios maestros; otros 100
tests de Dashboard, reglas de reservas, sincronización/parser iCal y caché
compartida. Ambas baterías superadas, con aviso preexistente Starlette/httpx.
Los 6 tests de rutas de revisión se repitieron tras reforzar la invalidación de
una ubicación verificada al editar la dirección (solapados, no sumar).
JavaScript: 7 tests superados. Revisión sintética HTTP 200. Integridad en lectura:
BD de negocio y caché con quick_check=ok y sin infracciones de claves foráneas.

## Incidencias administrativas

### Estado comprobado el 18/11/2026

Lectura de la caché compartida: ocho fincas publicadas verificadas, ninguna
pendiente. Las cuatro incidencias anteriores (Gerona 5, San Vicente 16,
Bisbe Winibal 7 y Clemente Gonzálvez Valls 37) están resueltas. La confirmación
de Gerona 5 corresponde a la ubicación concreta aprobada por el titular; no es
una traducción automática general. No se realizaron nuevas consultas al proveedor
para esta comprobación y las direcciones de negocio permanecieron intactas.

Al guardar una dirección diferente desde la revisión, su clave de caché cambia:
la coordenada anterior deja de aplicarse y aparece una incidencia pendiente.
El resultado anterior se conserva como historial. Una verificación posterior
retira automáticamente la incidencia abierta, sin editar estados manualmente.

El Dashboard integra las ubicaciones no verificadas como tipo `geolocation`,
una por finca (`geolocation:{property_id}`), con finca, dirección registrada,
motivo, estado y último intento en Europe/Madrid. No requiere ni realiza consultas
a Nominatim. No escribe estados en la BD ni en la caché.

Administración y worker deben compartir `PUBLIC_GEOCODING_CACHE` y, si se cambia,
`PUBLIC_GEOCODER_URL`. No se toma como fallback una caché de pruebas. Ambos
adaptadores productivos cargan la misma configuración persistente privada; sus
rutas y valores concretos permanecen en runtime, fuera de Git.
Sin caché ni configuración explícita no se generan alertas de un módulo no instalado.

La resolución es derivada: al verificar la dirección actual, desaparece de las
incidencias abiertas en la siguiente lectura. El sistema existente no tiene tabla
de incidencias ni historial de resoluciones; no se ha inventado uno. La caché
conserva claves de direcciones anteriores, pero no un historial de cada intento.
Al cambiar de dirección, vuelve a quedar pendiente hasta verificar la nueva.

Implementado y desplegado con el worker deshabilitado. No modifica el calendario de colaboradores, el
administrador, iCal ni la base de datos de negocio. No requiere migración.

## Fuente y disponibilidad

`PublicRoomService.list_rooms` continúa siendo la única selección de habitaciones.
El mapa proyecta exactamente sus resultados después de filtros de fechas y
características, publicación y ordenación. Usa Room.base_price y la misma foto
pública. Una consulta adicional agrupa por Property; no hay consultas por habitación.
No se exportan propietarios, inquilinos, reservas, identificadores internos,
planta, puerta ni datos económicos privados. Un marcador reúne las habitaciones
de una finca; su nombre público, fotografías, precios y enlaces proceden del catálogo.

## Geocodificación

Nominatim público, petición estructurada `street=numero calle`, `city=ciudad`.
Solo direcciones de fincas activas/publicadas, desde el servidor. Nunca peticiones
desde visitantes ni geocodificación en una petición HTTP del catálogo.
Se exige User-Agent identificativo. Proveedor configurable sin cambiar el cliente.

Política revisada: https://operations.osmfoundation.org/policies/nominatim/
API: https://nominatim.org/release-docs/latest/api/Search/

Caché SQLite privada separada, con WAL. Clave SHA-256 de proveedor, versión de
validación, calle, número y ciudad normalizados. Se conserva resultado, motivo,
fecha, intentos y coordenadas verificadas; no se guardan respuestas completas.
Los resultados correctos o ambiguos no se consultan repetidamente. Un cambio de
dirección produce una clave nueva: inmediatamente deja de mostrarse la coordenada
anterior, hasta verificar la nueva. No hay editor manual de coordenadas.

Verificación conservadora: ciudad equivalente (Elche/Elx), calle y número exactos
tras normalizar acentos, separadores y abreviaturas de vía. Más de una coordenada
coincidente significa ambigüedad. Sin número, calle o ciudad verificables no hay
marcador. No se usan centroides de ciudad/calle ni posiciones inventadas.

Las solicitudes se serializan mediante bloqueo SQLite, separadas por al menos
16 segundos; todas las instancias DEBEN compartir el mismo archivo de caché.
Se respeta así el límite conservador de 4 consultas/minuto para procesos periódicos.
Errores HTTP/red implican pausa global de 24 horas, máximo tres intentos por dirección.
Una dirección agotada no bloquea otras después del cooldown. Logs: solo id de finca
y estado; los motivos HTTP/timeout/conexión quedan en la caché privada, sin direcciones.
No borrar la caché para forzar reintentos. Es un servicio sin garantía de disponibilidad.

## Configuración de referencia

```text
PUBLIC_MAP_ENABLED=1
PUBLIC_GEOCODING_WORKER_ENABLED=0
PUBLIC_GEOCODING_CACHE=<ruta absoluta privada persistente>/locations.sqlite3
PUBLIC_GEOCODER_USER_AGENT=HSI-Rents/1.0 (https://hsi-rents.com/contacto)
PUBLIC_GEOCODER_URL=https://nominatim.openstreetmap.org/search
PUBLIC_MAP_TILE_URL=https://tile.openstreetmap.org/{z}/{x}/{y}.png
```

Flags desactivados por defecto. Si se habilita expresamente, el worker lee direcciones cada cinco minutos;
solo las claves nuevas o errores reintentables provocan tráfico. Usa la conexión
de negocio de SOLO LECTURA. Para precalentar una vez, con las mismas variables:
`python -m backend.public.map_worker`. No ejecutar copias con cachés independientes
contra el mismo proveedor en paralelo. El CLI muestra únicamente recuentos.

## Mapa, CSP y privacidad

Leaflet 1.9.4 fijado y servido localmente, licencia incluida. Se carga al abrir
el modal, no durante la navegación ordinaria. Teselas OSM sin precarga masiva,
sin descargas offline y con caché HTTP normal; atribución visible. Política:
https://operations.osmfoundation.org/policies/tiles/

Solo el catálogo habilitado amplía `img-src` al origen HTTPS concreto de las
teselas. No se relaja script-src, TrustedHost ni la CSP de colaboradores.
El referrer sigue siendo strict-origin-when-cross-origin. Política de privacidad
y cookies explican las conexiones a OSM al abrir el mapa, IP/metadatos y caché
HTTP. No analytics, almacenamiento de seguimiento ni cookies propias nuevas.
Privacidad del proveedor: https://osmfoundation.org/wiki/Privacy_Policy

El modal nativo retiene foco, admite Escape y devuelve foco/scroll al cerrar.
No cambia URL ni filtros. Fallos de JS/teselas muestran aviso y mantienen catálogo.

## Validación 12-11-2026

Consulta real controlada: 8 fincas; 4 verificadas, 1 sin coincidencia exacta,
1 error del proveedor y 2 no consultadas tras detener la tanda. El error de esa
primera consulta quedó con motivo genérico provider_unavailable; la implementación
posterior distingue HTTP, timeout y conexión para futuras incidencias. No se ha
repetido la consulta para diagnosticarlo ni se ha anulado el cooldown.
Previsualización local :8125: 4 marcadores, 16 habitaciones geolocalizadas;
19 habitaciones sin marcador permanecen en el catálogo (35 en total en esa lectura).

Tests Python con MockTransport: verificación, ambigüedad, caché, concurrencia,
throttle/cooldown, cambio de dirección, selección filtrada, agrupación, privacidad,
una sola consulta adicional y CSP. Tests Node ejecutan el script con DOM/Leaflet
simulados: carga diferida, apertura/cierre, foco/scroll, fichas/enlaces/precios,
sin ubicaciones y fallos de assets/teselas. Nunca geocodificación real en tests.

La validación visual manual del mapa fue aprobada posteriormente por el usuario.
La comprobación automatizada de navegador no se realizó porque el navegador local
estaba deshabilitado en Work; los tests DOM no se presentan como sustituto de ella.
El despliegue controlado posterior fue autorizado y ejecutado; el worker continúa
apagado. La configuración productiva y las copias de reversión no se versionan.

Resultados ejecutados: batería `tests/integration/public`: 73 passed; tras añadir
dos casos de filtrado/agrupación y concretar los motivos de error, batería específica
`test_catalog_map.py`: 8 passed (solapada, no sumar). JavaScript mapa + colaboradores:
16 passed. Aviso Python preexistente de deprecación Starlette/httpx. Integridad de
negocio en solo lectura: quick_check=ok, foreign_key_check=0. git diff --check sin
errores (solo avisos de normalización LF/CRLF).
