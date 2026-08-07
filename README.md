# RentalManager

RentalManager es una aplicación desarrollada en Python con FastAPI para la gestión de alquileres por habitaciones.

Su objetivo principal es centralizar la gestión de habitaciones y sincronizar calendarios iCal procedentes de distintas plataformas de alquiler, ofreciendo una visión unificada de la disponibilidad.

---

# Estado del proyecto

Actualmente el proyecto se encuentra en fase de desarrollo activo.

## Funcionalidades implementadas

- Gestión de propiedades.
- Gestión de habitaciones.
- Workspace de habitación.
- Arquitectura por capas:
  - Models
  - Repositories
  - Services
  - Routers
- Migraciones de base de datos mediante Alembic.

## En desarrollo

- Gestión de reservas (Booking).
- Integración de calendarios iCal.
- Sincronización automática entre plataformas.
- Gestión de huéspedes.
- Estado de sincronización.
- Dashboard de disponibilidad.

---

# Arquitectura

```
FastAPI
│
├── API Routers
├── Services
├── Repositories
├── Models
└── SQLite
```

El proyecto sigue una arquitectura por capas donde:

- Los **Models** representan el dominio.
- Los **Repositories** encapsulan el acceso a datos.
- Los **Services** contienen la lógica de negocio.
- Los **Routers** gestionan las peticiones HTTP.

---

# Modelo de dominio

```
Property
    │
    ▼
Room
    │
    ├──────────────┐
    ▼              ▼
RoomCalendar    Booking
    │              │
    ▼              ▼
Platform       Guest
```

El núcleo del sistema es la **habitación**.

Toda la información operativa gira alrededor de ella.

---

# Tecnologías

- Python
- FastAPI
- SQLAlchemy
- SQLite
- Alembic
- Jinja2
- Bootstrap 5

---

# Base de datos

Las modificaciones del esquema se realizan mediante Alembic.

Flujo habitual:

```bash
alembic revision --autogenerate -m "Descripción"
alembic upgrade head
```

No se recomienda modificar la base de datos manualmente.

---

# Filosofía del proyecto

RentalManager busca ser una herramienta especializada para la gestión de alquileres por habitaciones.

Los principios que guían el desarrollo son:

- Simplicidad.
- Arquitectura limpia.
- Evitar duplicar información.
- No almacenar datos que puedan calcularse.
- Separación clara entre configuración y operación.
- Mantener una interfaz rápida y enfocada al trabajo diario.

---

# Roadmap

## DEV-009

- Implementar Booking.

## DEV-010

- Gestión de huéspedes.

## DEV-011

- Configuración de calendarios.

## DEV-012

- Sincronización iCal.

## DEV-013

- Dashboard de disponibilidad.

---

# Licencia

Proyecto privado.
