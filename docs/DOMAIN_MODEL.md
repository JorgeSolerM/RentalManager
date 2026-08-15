# Modelo de Dominio (Domain Model)

Versión: 1.0

---

# Objetivo

Definir las entidades principales de RentalManager y las relaciones entre ellas.

Este documento representa el modelo de negocio de la aplicación.

No describe la base de datos.

---

# Modelo general

```
                    +------------------+
                    |    Propiedad     |
                    |    (Property)    |
                    +------------------+
                              |
                              | 1..N
                              |
                    +------------------+
                    |   Habitación     |
                    |      (Room)      |
                    +------------------+
                       |            |
                  1..N |            | 1..N
                       |            |
          +----------------+   +----------------+
          | RoomCalendar   |   |    Reserva     |
          +----------------+   +----------------+
                  |                     |
                  | N..1                | N..1
                  |                     |
          +----------------+   +----------------+
          | Plataforma     |   |    Huésped     |
          |  (Platform)    |   |    (Guest)     |
          +----------------+   +----------------+
```

---

# Entidades

## Property

Representa un inmueble gestionado por RentalManager.

Contiene una o varias habitaciones.

---

## Room

Representa la unidad alquilable.

Toda reserva pertenece a una habitación.

Toda sincronización pertenece a una habitación.

Cada habitación genera un único calendario maestro.

Una habitación inactiva conserva sus reservas e histórico, pero no puede recibir nuevas reservas.

---

## Platform

Representa una plataforma externa incluida en un catálogo configurable.

Ejemplos:

- HousingAnywhere
- Airbnb
- Booking
- Flatio
- Spotahome

La vinculación y configuración de una plataforma para una habitación se realiza mediante un calendario de habitación (RoomCalendar). Cada configuración podrá tener:

- URL iCal
- Estado
- Última sincronización
- Configuración propia

---

## Booking

Representa una reserva.

Puede proceder de:

- iCal
- creación manual
- futuras APIs

Las reservas manuales requieren huésped. Las reservas importadas pueden tener inicialmente un huésped desconocido.

No pueden solaparse dos reservas de una misma habitación. RentalManager no permite forzar un solapamiento manualmente.

Una reserva importada sigue perteneciendo conceptualmente a su plataforma o calendario de origen. RentalManager no la sobrescribe ni cancela de forma arbitraria.

El precio se expresa como precio mensual. No forman parte del modelo actual el precio diario, el importe total de la estancia, los descuentos ni las comisiones.

---

## Synchronization Engine

No forma parte del modelo de datos.

Es un servicio.

Su misión consiste en:

- importar calendarios;
- detectar cambios;
- actualizar reservas;
- generar el calendario maestro.

---

# Relaciones

Una propiedad contiene muchas habitaciones.

Una habitación pertenece siempre a una única propiedad.

Una habitación puede configurarse con muchas plataformas mediante RoomCalendar.

Una habitación puede tener muchas reservas.

Una plataforma forma parte de un catálogo global y puede configurarse en muchas habitaciones.

Cada reserva pertenece a una única habitación.

Las entidades con relaciones o histórico se archivan o desactivan; no se eliminan físicamente mientras su histórico deba conservarse.

---

# Principios

El motor de sincronización está desacoplado del modelo.

Esto permitirá sustituir iCal por APIs en el futuro sin modificar las entidades principales.

---

# Evolución prevista

En futuras versiones podrán incorporarse nuevas entidades:

- Owner
- Cleaning
- Maintenance
- Incident
- Statistics
- Documents

Sin modificar la arquitectura principal.

---

# Regla de oro

Toda nueva funcionalidad deberá integrarse respetando este modelo.

Si una funcionalidad obliga a romper estas relaciones, deberá replantearse su diseño antes de implementarse.
