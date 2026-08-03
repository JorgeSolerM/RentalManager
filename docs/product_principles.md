# RentalManager - Product Principles

**Versión:** 1.0

**Estado:** Activo

**Última revisión:** 2026-08-04

---

# Objetivo

Este documento recoge los principios que definen el comportamiento de RentalManager.

No describe cómo está implementado el software.

Describe cómo debe comportarse el producto.

---

# RM-001

Conservación de la información.

Toda entidad sigue el ciclo:

Activa

↓

Archivada

↓

Eliminada

---

# RM-002

Las acciones destructivas no forman parte de la interfaz cotidiana.

El usuario trabaja con elementos activos.

Las operaciones de eliminación estarán alejadas de las acciones habituales.

---

# RM-003

La simplicidad tiene prioridad.

Solo se añadirá complejidad cuando resuelva un problema real.

---

# RM-004

La interfaz debe favorecer las operaciones frecuentes.

Las operaciones excepcionales permanecerán ocultas hasta ser necesarias.

---

# RM-005

Los componentes deben ser reutilizables.

Antes de crear una nueva solución se evaluará si puede construirse como un componente RM UI.

---

# RM-006

La aplicación debe minimizar el número de clics necesarios para realizar una tarea habitual.

---

# RM-007

La interfaz nunca debe engañar al usuario.

Si una operación falla, la interfaz volverá inmediatamente al estado anterior.

---

# RM-008

El historial tiene valor.

Siempre que sea posible los datos se conservarán.

---

# RM-009

La seguridad tiene prioridad sobre la rapidez en las operaciones destructivas.

---

# RM-010

RentalManager no intenta impresionar.

Intenta resultar cómodo durante horas de trabajo continuado.

---

# Historial

2026-08-04

Creación del documento.
