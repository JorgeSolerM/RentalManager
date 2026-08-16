# Modelo de Base de Datos

Versión: 1.1

---

# Objetivo

Definir la estructura de la base de datos de RentalManager.

Este documento describe únicamente la persistencia de datos.

No define reglas de negocio.

---

# Tablas

La versión 1.0 utilizará las siguientes tablas.

Property

Room

Platform

RoomCalendar

Guest

Booking

---

# Relación general

Property 1 ── N Room

Room 1 ── N RoomCalendar N ── 1 Platform

Room 1 ── N Booking

Guest 1 ── N Booking

RoomCalendar 1 ── N Booking

---

# Tabla Property

Representa un inmueble.

Campos

- id (INTEGER)
- name
- alias
- address
- city
- owner
- notes
- active

---

# Tabla Room

Representa una habitación.

Campos

- id (INTEGER)
- property_id
- code
- display_order
- base_price
- square_meters
- active

Observaciones

base_price representa el precio mensual habitual de la habitación.

El precio de una reserva se expresa como precio mensual. No se contemplan por ahora precios diarios, importe total de estancia, descuentos ni comisiones.

---

# Tabla Platform

Representa una plataforma incluida en un catálogo configurable.

Ejemplos

- HousingAnywhere
- Booking
- Airbnb
- Flatio
- Spotahome
- Manual
- Directo

Campos

- id (INTEGER)
- name
- slug (único)
- favicon
- supports_import
- supports_export
- active

La plataforma no pertenece directamente a una única habitación. Su configuración por habitación se representa mediante RoomCalendar.

---

# Tabla RoomCalendar

Representa la configuración de una plataforma para una habitación.

Campos

- id (INTEGER)
- room_id
- platform_id
- import_url
- export_url
- active
- last_sync_at

Existe una única configuración para cada pareja `room_id` y `platform_id`.

Una configuración requiere al menos una URL HTTP/HTTPS compatible con las capacidades de su Platform. Puede desactivarse sin eliminar sus reservas históricas y solo puede borrarse si nunca ha tenido reservas.

---

# Tabla Guest

Representa a un huésped asociado a una o varias reservas.

Campos

- id (INTEGER)
- full_name
- display_name
- phone
- email
- notes
- active

---

# Tabla Booking

Representa una reserva.

Campos

- id (INTEGER)
- room_id
- room_calendar_id
- guest_id
- origin
- external_reference
- check_in
- check_out
- price
- notes

Las reservas manuales requieren huésped. Las reservas importadas pueden mantener un huésped desconocido hasta disponer de sus datos.

No pueden existir reservas con periodos solapados para la misma habitación.

Las reservas importadas nuevas se identifican de forma idempotente mediante la pareja `room_calendar_id` y `external_reference`. Esta pareja es única cuando ambos valores son no nulos; las reservas históricas con referencia nula se conservan fuera del mecanismo idempotente.

SQLite aplica triggers en INSERT y UPDATE para garantizar los intervalos semiabiertos `[check_in, check_out)` incluso ante escrituras concurrentes.

---

# Relaciones

Una propiedad contiene muchas habitaciones.

Una habitación pertenece a una única propiedad.

Una habitación puede tener muchas plataformas mediante RoomCalendar.

Una habitación puede tener muchas reservas.

Una plataforma puede configurarse en muchas habitaciones.

Cada reserva pertenece a una única habitación.

Las entidades con relaciones o histórico se conservan mediante archivado o desactivación. No se realiza borrado físico mientras ese histórico deba preservarse.

---

# Decisiones de diseño

No existe un campo "channel".

El origen de la reserva siempre será una Platform.

El calendario maestro pertenece a la habitación.

La URL del calendario maestro nunca cambia.

El contenido del calendario sí cambia.

Las reservas importadas pertenecen conceptualmente a su origen y no deben sobrescribirse ni cancelarse arbitrariamente desde RentalManager.

---

# Evolución prevista (2.0)

La arquitectura queda preparada para incorporar nuevas tablas.

BookingDeposit

Owner

Cleaning

Maintenance

Incident

Statistics

Documents

Estas tablas se añadirán sin modificar las relaciones principales del modelo.

---

# Principios

La base de datos deberá permanecer simple.

Cada tabla tendrá una única responsabilidad.

Las relaciones deberán minimizar la duplicación de información.

Toda nueva funcionalidad deberá respetar este modelo.
