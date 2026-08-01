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
          | Plataforma     |   |    Reserva     |
          |  (Platform)    |   |   (Booking)    |
          +----------------+   +----------------+
                       \            /
                        \          /
                         \        /
                          \      /
                    +----------------------+
                    | Motor de Sincronización |
                    +----------------------+
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

---

## Platform

Representa una plataforma externa.

Ejemplos:

- HousingAnywhere
- Airbnb
- Booking
- Flatio
- Spotahome

Cada plataforma podrá tener:

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

Todas las reservas se gestionan exactamente igual.

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

Una habitación puede tener muchas plataformas.

Una habitación puede tener muchas reservas.

Cada plataforma pertenece a una única habitación.

Cada reserva pertenece a una única habitación.

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
