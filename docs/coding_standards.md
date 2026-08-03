# RentalManager - Coding Standards

**Versión:** 1.0

**Estado:** Activo

**Última revisión:** 2026-08-04

---

# Objetivo

Definir las normas de desarrollo del proyecto.

Estas normas buscan mantener un código homogéneo, sencillo y fácil de mantener.

---

# Organización

Repository

↓

Service

↓

Router

Nunca se debe invertir esta dependencia.

---

# Archivos

Siempre que sea posible se trabajará sustituyendo archivos completos.

Esta metodología evita desincronizaciones entre versiones.

---

# Componentes

Todo componente reutilizable tendrá:

- HTML
- CSS
- JavaScript

independientes.

---

# CSS

Se utilizará:

theme.css

para variables globales.

Cada componente dispondrá de su propio CSS.

---

# JavaScript

Cada módulo tendrá un archivo propio.

Ejemplo:

properties.js

No se mezclará lógica de diferentes módulos.

---

# Services

Toda regla de negocio pertenece al Service.

Nunca al Router.

---

# Repository

El Repository solo accede a la base de datos.

Nunca toma decisiones.

---

# Nombres

Los nombres deben ser claros.

Se evitarán abreviaturas innecesarias.

---

# Commits

Cada sprint terminado debe finalizar con:

git add .
git commit
git push

No se dejarán cambios importantes sin proteger mediante Git.

---

# Desarrollo

Antes de añadir complejidad se buscará siempre la solución más sencilla.

La reutilización tendrá prioridad sobre la duplicación.

---

# Historial

2026-08-04

Creación del documento.
