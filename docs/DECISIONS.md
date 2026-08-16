# Registro de decisiones

---

## DEC-001

Fecha: 01/08/2026

Todas las claves primarias utilizarán INTEGER AUTOINCREMENT.

Motivo:

La aplicación utiliza SQLite local.

UUID no aporta ventajas en la versión 1.x.

---

## DEC-002

El calendario maestro tendrá una URL permanente.

Nunca cambiará.

Solo cambiará su contenido.

---

## DEC-003

No existe el concepto "Channel".

Toda reserva pertenece a una Platform.

---

## DEC-004

Las fechas nunca podrán modificarse arrastrando una reserva.

Siempre se utilizará un selector de fechas.

---

## DEC-005

RentalManager siempre abrirá en un estado conocido.

No recuperará la sesión anterior.

---

## DEC-006

El Gantt utilizará filas compactas por defecto.

El espacio vertical tiene prioridad.

---

## DEC-007

Cada fila del Gantt será autoexplicativa.

Formato:

Nombre corto de la propiedad · Código de habitación.

Ejemplo:

Universidad · H01

---

## DEC-008

Fecha: 15/08/2026

Las entidades con relaciones o histórico se conservarán mediante archivado o desactivación.

No se realizará borrado físico de propiedades, habitaciones, plataformas, calendarios ni otros registros cuyo histórico deba preservarse.

Motivo:

El histórico operativo debe permanecer consultable y las relaciones existentes no pueden perder su significado.

---

## DEC-009

Fecha: 15/08/2026

Una habitación inactiva conservará sus reservas e histórico, pero no podrá recibir nuevas reservas.

---

## DEC-010

Fecha: 15/08/2026

RentalManager impedirá cualquier solapamiento entre reservas de la misma habitación.

No existirá una opción para forzar manualmente un solapamiento.

---

## DEC-011

Fecha: 15/08/2026

Las reservas importadas pertenecen conceptualmente a su plataforma o calendario de origen.

RentalManager no las sobrescribirá ni cancelará arbitrariamente. Las modificaciones o cancelaciones en una plataforma externa seguirán el protocolo de dicha plataforma.

---

## DEC-012

Fecha: 15/08/2026

El catálogo de plataformas será configurable y no estará limitado a un conjunto cerrado de plataformas.

---

## DEC-013

Fecha: 15/08/2026

Las reservas manuales requerirán un huésped.

Las reservas importadas podrán conservar un huésped desconocido hasta que se disponga de información suficiente para identificarlo.

---

## DEC-014

Fecha: 15/08/2026

El precio de una reserva se expresará como precio mensual.

No se implementarán por ahora precios diarios, importe total de estancia, descuentos ni comisiones.

---

## DEC-015

Fecha: 16/08/2026

La detección de solapamientos se realizará inicialmente dentro de la frontera
transaccional del servicio mediante una consulta de intervalos semiabiertos.

Esta protección mantiene los casos de uso ordinarios, pero no cierra por sí sola
la carrera entre dos escrituras concurrentes que validen antes de que ninguna se
confirme. Antes de automatizar iCal o cualquier sincronización externa deberá
incorporarse una garantía de concurrencia en la base de datos o una serialización
equivalente de las escrituras de reservas.

---

## DEC-016

Fecha: 16/08/2026

Antes de habilitar sincronizaciones externas, SQLite protegerá los solapamientos
mediante triggers en INSERT y UPDATE con intervalos semiabiertos. La validación
del servicio se conserva para ofrecer errores de dominio legibles.

Las reservas importadas nuevas requieren una referencia externa estable y se
identifican por `(room_calendar_id, external_reference)`. Un índice único parcial
protege esa identidad cuando ambos valores son no nulos. Las referencias nulas
históricas se conservan, pero no participan en actualizaciones idempotentes.

RoomCalendar mantiene la configuración y el histórico de una Platform para una
Room. Puede desactivarse sin destruir datos y solo puede borrarse cuando nunca ha
tenido Bookings.

---

## DEC-017

Fecha: 16/08/2026

RentalManager ofrece un único calendario maestro por Room. `RoomCalendar` solo
almacena la URL externa importada desde una Platform y no contiene una URL de
exportación por plataforma. `supports_export` indica que la Platform puede
consumir el calendario maestro; una Platform solo exportadora puede configurarse
sin `import_url`.

---

## DEC-018

Fecha: 16/08/2026

La primera importación iCal es manual, idempotente por
`(room_calendar_id, external_reference)` y atómica para el feed completo. Las
descargas validan cada destino y redirección contra SSRF y fijan la IP validada
durante la conexión, conservando el hostname para Host y TLS/SNI.

En eventos all-day, el `DTEND` exclusivo de iCal se convierte a la fecha real de
salida mediante `check_out = DTEND - 1 día`; las estancias resultantes de una
sola jornada son incompatibles. Los eventos con hora se convierten a
`Europe/Madrid` sin esa resta. No se admiten recurrencias. Los eventos cancelados y los que
desaparecen del feed se conservan como Bookings y se notifican como advertencias;
no se implementa aún el ciclo de vida necesario para liberar esas fechas.

HousingAnywhere identifica huéspedes mediante el patrón específico
`Reservas: <nombre>` de `SUMMARY`. El nombre normaliza espacios y usa la
reutilización exacta existente de Guest, incluso si solo contiene un nombre de
pila. Los textos de bloqueo catalogados no crean Guests, `DESCRIPTION` no se usa
como identidad y una Booking que ya tenga Guest no se reasigna automáticamente.

---

## DEC-019

Fecha: 16/08/2026

Cada Room publica un calendario maestro mediante un token aleatorio persistente,
revocable y ajeno a su ID. Para evitar bucles sin crear configuraciones de
exportación por RoomCalendar, la URL incorpora la plataforma consumidora y esa
vista excluye únicamente las reservas importadas desde dicha plataforma. Incluye
las reservas manuales y las procedentes de las demás plataformas.

Cada Booking tiene un UID iCal opaco y estable, independiente del token de la
Room. El feed publica exclusivamente UID, DTSTAMP, DTSTART, DTEND, SUMMARY
neutro, STATUS y TRANSP. La fecha real de salida se transforma al límite
exclusivo RFC 5545 mediante `DTEND = check_out + 1 día`. Por ello, dos reservas
contiguas según la regla interna pueden ocupar el mismo día límite en el feed;
esta diferencia es deliberada y conserva el significado de salida real.

Las URLs solo se construyen desde `PUBLIC_BASE_URL`; nunca desde el encabezado
Host de una petición. Una Room inactiva mantiene accesible su ocupación y la
regeneración del token revoca inmediatamente todas sus vistas anteriores.
