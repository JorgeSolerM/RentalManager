# RentalManager - Arquitectura

**Versión:** 1.0

**Estado:** Activo

**Última revisión:** 2026-08-04

---

# Objetivo

Este documento describe la arquitectura general de RentalManager.

No define reglas de programación ni decisiones de producto.

Su objetivo es explicar cómo está organizado el software y cuáles son las responsabilidades de cada una de sus capas.

---

# Filosofía

RentalManager está construido siguiendo una arquitectura por capas.

Cada capa tiene una única responsabilidad y nunca debe asumir funciones propias de otra.

La comunicación siempre fluye en la misma dirección.

Browser
↓
JavaScript
↓
Router
↓
Service
↓
Repository
↓
Database

---

# Estructura del proyecto

backend/

    api/
        routers/

    services/

    repositories/

    models/

    templates/

    static/

docs/

---

# Responsabilidades

## Router

Responsable de recibir las peticiones HTTP.

Debe contener la mínima lógica posible.

Su trabajo consiste en:

- validar la petición
- obtener la sesión
- llamar al Service correspondiente
- devolver la respuesta

Nunca contiene reglas de negocio.

---

## Service

Es el núcleo de la aplicación.

Aquí vive toda la lógica de negocio.

Ejemplos:

- activar una propiedad
- archivar una habitación
- sincronizar calendarios

El Service nunca conoce detalles de la interfaz.

---

## Repository

Es la única capa que accede directamente a la base de datos.

Contiene operaciones CRUD.

Nunca contiene reglas de negocio.

---

## Models

Representan las entidades persistentes.

Su responsabilidad es describir la estructura de los datos.

---

## Templates

Contienen únicamente presentación.

No contienen lógica de negocio.

---

## JavaScript

Cada página posee su propio controlador JavaScript.

Ejemplo:

properties.js

Su responsabilidad consiste en:

- gestionar eventos
- comunicarse con el backend
- actualizar la interfaz

---

# Componentes RM UI

RentalManager dispone de una biblioteca propia de componentes reutilizables.
```
