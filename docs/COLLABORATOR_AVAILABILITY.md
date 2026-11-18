# Calendario público de colaboradores

## Acceso aprobado

El 29/10/2026 se autoriza sustituir el enlace secreto por acceso completamente
público. `/colaboradores/disponibilidad` y su endpoint GET `/data` funcionan sin
token, sesión, cookie ni contraseña. Las variables antiguas
COLLABORATOR_CALENDAR_TOKEN_SHA256 y COLLABORATOR_CALENDAR_TOKEN_HASH_FILE ya no
intervienen. El fragmento de los enlaces antiguos no se lee ni envía.
Compartir únicamente la URL sin fragmento.

## Selección (sin cambios)

- Horizonte `[hoy, hoy + seis meses naturales)`, fecha Europe/Madrid.
- Todas las reservas con salida posterior a hoy, sin límite superior.
- `available_from = max(hoy, salidas efectivas de todas esas reservas)`.
- Incluir solo si available_from pertenece al horizonte. Nunca ofrecer huecos
  intermedios; los días anteriores a la disponibilidad terminal se representan
  en rojo como disponibilidad no ofrecida, aunque existan huecos entre reservas.
- Ocupación `[check_in, check_out)`: el día de salida ya está libre.
- Finalizaciones anticipadas confirmadas usan check_out efectivo, no fin
  económico ni mera previsión de salida. Reservas iCal cuentan igualmente.
- Publicabilidad efectiva de Room, Finca y gestor; no basta is_published.
- El número es dinámico; 21 corresponde a la comprobación del despliegue,
  no es un límite ni un valor fijado en código.

## Arquitectura y privacidad

Aplicación pública separada; repositorio público existente y helper terminal.
No se cambia la lógica de huecos del catálogo ordinario. Sin tablas, migraciones
ni dependencias nuevas. Conexión pública SQLite mode=ro y rutas exclusivamente
GET; POST/PUT/PATCH/DELETE devuelven 405. No se monta administración ni API interna.
Solo nombres públicos, slugs, fechas, precio mensual anunciado, portada pública
y URL real del anuncio: no personas, IDs de reservas, notas, contratos, importes
contractuales ni configuración interna. Las fechas de ocupación
pasan a ser consultables por cualquiera por decisión expresa del titular.

Sin cookies, almacenamiento del navegador ni analítica. Se conserva no-store,
no-referrer, CSP, nosniff, protección de frames y noindex/nofollow/noarchive.
Sin sitemap/menús. Noindex no es una protección de acceso ni evita copias de
información pública por terceros.

## Interfaz

Tabla semanal agrupada por finca, etiquetas fijas y scroll interno en escritorio.
Hasta 768 px se muestra un mes, con navegación y semanas en una única cabecera
sticky junto a los controles de ordenación. Rangos y disponibilidad mediante
texto accesible y tooltip, además del color y la leyenda; sin edición.
Refresco cada 60 segundos; un
fallo retira datos obsoletos. El **nombre de cada habitación** enlaza a SU anuncio
`/habitaciones/{slug}`, en pestaña nueva, con noopener/noreferrer y «Ver anuncio
de esta habitación». La finca queda como información de agrupación.

### Precio mensual

`price_monthly` procede de `Room.base_price`, la misma fuente del precio público
del anuncio; no de `Booking.price` ni de condiciones económicas de reservas.
Se muestra justo debajo del nombre, sin enlace y separado de la miniatura,
con formato español y sufijo `€/mes` (por ejemplo, `395 €/mes`).
`Consultar precio` es una alternativa defensiva de presentación: no modifica
la regla de publicabilidad existente, que exige un precio finito y positivo.
La fecha de disponibilidad aparece después del precio. La portada y el nombre
conservan su enlace al anuncio; no se duplican datos ni se modifica la BD.

## Despliegue y rollback

La entrega inicial utilizó un runtime aislado basado en 11976ad015627cd5232199ed7aecf24371f3cde8
(pre-fiscal), con componentes públicos revisados superpuestos. No desplegar ni
hacer push indiscriminado de agente-ia, que contiene también preparación fiscal.
Para una publicación futura se debe identificar la entrega activa y respaldarla;
la referencia histórica anterior no sustituye esa comprobación.
Un adaptador privado conecta BD/media productivas sin cargar administración.
El lanzador apunta a esa entrega, no al checkout. No se necesita secreto.

Respaldar entrega/lanzador, probar en loopback temporal y recargar solo la tarea
pública, manteniendo 127.0.0.1:8001. No tocar DNS, Cloudflare, administración,
iCal ni migraciones. Verificar HTTPS real, no solo localhost.
Conservar rollback a la entrega privada anterior y el rollback original sin
calendario. Restaurar lanzador y reiniciar solo la tarea pública si es necesario.
El antiguo hash queda solo en la copia privada: cambiarlo NO revoca el acceso
al nuevo calendario público. Para retirarlo se debe retirar/restaurar la entrega.

## Pruebas

### Presentación semanal y portadas (29/10/2026)

Actualización responsive: hasta 768 px se presenta un mes seleccionado, con
semanas alineadas debajo de la identidad de cada habitación. Flechas accesibles
recorren los meses disponibles, conservando la selección tras el refresco.
El primer/último mes puede tener menos de cuatro semanas por el recorte del
horizonte; no se inventan fechas fuera del período. En escritorio siguen visibles
las semanas del horizonte con scroll interno y navegación a cada grupo mensual.

Cabecera móvil unificada: ordenación, navegación y semanas comparten un único contenedor
sticky opaco de altura estable. El thead de escritorio se oculta en móvil, sin
dos cabeceras superpuestas. La marca global no es fija. Cambiar de mes conserva
la posición vertical y no reconstruye las filas; el anclaje automático está
desactivado dentro de la vista. Comprobado con clics reales al final de la lista
en 375 y 768 px, y regresión de escritorio en 1280 px.

El texto enlazado es `Room.public_slug`, sin modificar slug ni URL. Se conserva
el título como alternativa defensiva; la publicabilidad actual exige slug.
Cada bloque semanal es un SVG compacto de tamaño uniforme: tramos contiguos
verdes/rojos, agrupando días consecutivos iguales en orden cronológico. No hay
amarillo ni separación interna. El texto accesible indica rango y proporción.
No se requiere CSS inline ni se relaja CSP.

La proyección incluye únicamente la URL pública de la portada de 320 px,
resuelta por el mismo servicio del anuncio (portada de habitación y alternativa
de finca). No se duplican imágenes. Miniatura y nombre comparten enlace al anuncio.
Si falta o falla la imagen, queda un marcador neutro.

La vista agrupa lunes–domingo por el mes de su lunes; los rangos visibles
identifican semanas entre meses. En los extremos solo cuenta los días consultados,
marcados con asterisco. Verde requiere disponibilidad ofrecida para ese día;
el resto es rojo. Los huecos previos a available_from no se ofrecen ni se pintan libres.
La fecha exacta sigue bajo el nombre. No cambia la selección ni los intervalos.
La tabla conserva scroll interno, nombres fijos y refresco de un minuto.

Tests semanales: cambio de mes, semana parcial, salida exclusiva, huecos no
ofrecidos, semana completa, portada reutilizada y ausencia de imagen.

Integración: ejemplos aprobados, reservas lejanas, publicación, salida anticipada,
iCal, solapamientos, enlaces, DTO mínimo, acceso anónimo, configuración obsoleta
ignorada y rechazo de todos los métodos de escritura.
JavaScript: GET sin Authorization/credenciales, nombre enlazado, ausencia de token
en DOM/enlaces, huecos no ofrecidos en rojo, salida exclusiva y refresco.
Validación externa: HTTPS sin cookies/Authorization, anuncios, responsive
375/768/1280, consola, aislamiento administrativo e integridad BD.
Fixtures sintéticos; runtime y evidencias privadas excluidos de Git.

### Ordenación y cabecera móvil (2026-10-30)

El selector segmentado comienza en «Por finca», conservando exactamente el orden
y agrupación recibidos. «Por disponibilidad» muestra una lista global: disponibles
desde hoy primero; después fechas futuras ascendentes; sin fecha ofrecida dentro
del horizonte al final. Los empates se resuelven por slug y URL. Se usa `start`
(hoy en Madrid) y `available_from` del servicio, nunca el mes visualizado ni huecos
intermedios. No se añaden habitaciones excluidas por el servicio.

Se reordenan los mismos nodos de filas, conservando enlaces, imágenes y mes.
El cambio de orden toma como referencia la primera fila visible y conserva su
posición cuando los límites de scroll lo permiten. Cerca del principio/final,
el navegador limita naturalmente el desplazamiento al espacio disponible.
La selección se mantiene durante el refresco automático, pero no se persiste.

Hasta 768 px, un único contenedor sticky opaco incluye selector, navegación y
semanas (aproximadamente 144 px). No hay cabecera global fija que compensar.
El escritorio conserva la tabla desplazable. No se añaden escrituras ni storage.

Validación: 29 tests Python de integración pública y 11 tests JavaScript;
orden original/restauración, fecha/slug, ausencia de fecha, independencia del mes,
refresco, privacidad y métodos de escritura rechazados. Comprobación de navegador
375/768/1280. Despliegue público aislado, conservando release y lanzador anteriores
para rollback; sin cambiar administración, iCal, facturación ni datos de negocio.

### Revisión aislada del bloque pendiente (18/11/2026)

Se revisaron los ocho archivos del calendario sobre una copia de HEAD, sin
incorporar los cambios pendientes de geolocalización. Resultado: **106 tests
Python y 12 tests JavaScript superados**, además de `git diff --check`.
La batería Python incluyó integración pública, disponibilidad, geometría Gantt,
rutas Gantt y calendarios maestros; JavaScript cubrió el calendario de colaboradores.

Las comprobaciones de navegador descritas en las secciones anteriores son
históricas. En esta revisión no se repitió la validación visual real en
375/768/1280 px: el acceso a la herramienta de navegador falló. Los timeouts
HTTPS intermitentes observados se investigan separadamente y no se consideran
una regresión demostrada del calendario. Esta revisión no despliega código.
