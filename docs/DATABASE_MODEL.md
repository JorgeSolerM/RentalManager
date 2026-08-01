# Modelo de Base de Datos

Versión: 1.0

---

# Objetivo

Definir la estructura de la base de datos de RentalManager.

Este documento describe únicamente la persistencia de datos.

No define reglas de negocio.

---

# Tablas

La versión 1.0 utilizará las siguientes tablas.

Property

↓

Room

↓

Platform

↓

Booking

↓

AppSettings

---

# Relación general

Property

1

↓

N

Room

1

↓

N

Platform

1

↓

N

Booking

---

# Tabla Property

Representa un inmueble.

Campos

- id (UUID)
- name
- short_name
- owner
- address
- city
- active
- sort_order
- notes

---

# Tabla Room

Representa una habitación.

Campos

- id (UUID)
- property_id
- code
- name
- active
- sort_order
- default_price
- notes

Observaciones

default_price representa el precio habitual de la habitación.

Las reservas podrán modificar dicho importe.

---

# Tabla Platform

Representa el origen de una reserva.

Ejemplos

- HousingAnywhere
- Booking
- Airbnb
- Flatio
- Spotahome
- Manual
- Directo

Campos

- id (UUID)
- room_id
- name
- ical_url
- enabled
- sync_status
- last_sync
- notes

---

# Tabla Booking

Representa una reserva.

Campos

- id (UUID)
- room_id
- platform_id
- start_date
- end_date
- guest_name
- price
- status
- notes
- imported_uid
- imported_summary
- manual_override
- locked
- created_by
- created_at
- updated_at

---

# Tabla AppSettings

Configuración general de la aplicación.

Campos

- key
- value

Ejemplos

theme

row_height

agenda_days

language

---

# Relaciones

Una propiedad contiene muchas habitaciones.

Una habitación pertenece a una única propiedad.

Una habitación puede tener muchas plataformas.

Una habitación puede tener muchas reservas.

Cada plataforma pertenece a una única habitación.

Cada reserva pertenece a una única habitación.

---

# Decisiones de diseño

No existe un campo "channel".

El origen de la reserva siempre será una Platform.

El calendario maestro pertenece a la habitación.

La URL del calendario maestro nunca cambia.

El contenido del calendario sí cambia.

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
