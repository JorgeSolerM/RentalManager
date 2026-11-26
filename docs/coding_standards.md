# RentalManager - Coding Standards

**Versión:** 1.1

**Estado:** Activo

**Última revisión:** 2026-11-26

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

Aplicar cambios acotados y revisables, conservando el trabajo pendiente ajeno.
La entrega de un archivo completo no justifica sobrescribir cambios posteriores.

---

# Componentes

Separar HTML, CSS y JavaScript cuando cada parte sea necesaria. Reutilizar los
componentes compartidos; no crear archivos vacíos ni capas solo por uniformidad.

---

# CSS

Se utilizará:

theme.css

para variables globales.

Reutilizar los estilos compartidos. Crear CSS propio solo cuando el componente
lo necesite; no duplicar reglas para cumplir una separación artificial.

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

Preparar commits por funcionalidad, revisando el índice y excluyendo cambios
ajenos, datos y secretos. Commit, push y despliegue requieren autorización de la
tarea; un candidato aislado no autoriza su publicación. No usar `git add .`
cuando existan desarrollos pendientes.

---

# Desarrollo

Principios permanentes aplicables a todos los desarrollos:

- Buscar primero funciones, servicios y componentes existentes y reutilizarlos.
- No duplicar lógica de negocio; mantener una fuente de cálculo y validación.
- Priorizar soluciones sencillas, legibles, mantenibles y proporcionadas a la
  necesidad real. Evitar abstracciones, capas y funcionalidades sobredimensionadas.
- Eliminar código obsoleto solo cuando sea seguro y su ausencia esté comprobada.
- No introducir dependencias sin justificar necesidad, alternativas y coste.
- Evitar crecimiento injustificado de archivos o módulos; justificar cualquier
  incremento relevante de complejidad y los nuevos componentes.
- Informar por separado de líneas añadidas, eliminadas y saldo neto de código
  productivo (incluidas migraciones), pruebas y documentación. Indicar referencia,
  alcance y trabajo previo recuperado; no contabilizar artefactos o datos generados.
- No reducir líneas artificialmente a costa de legibilidad, seguridad o cobertura.

La revisión de reutilización dentro de una subfase no sustituye ni adelanta la
auditoría integral prevista en el [roadmap](roadmap.md).

---

# Historial

2026-08-04

Creación del documento.

2026-11-26: principios permanentes de proporcionalidad, reutilización y medición; publicación y cambios acotados.
