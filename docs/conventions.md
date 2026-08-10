# Convenciones de Desarrollo de RentalManager

## Objetivo

Este documento recoge las normas de desarrollo del proyecto.

Su finalidad es mantener un código uniforme, legible y fácil de mantener.

Las convenciones aquí descritas deberán respetarse en todas las nuevas funcionalidades.

---

# Principio general

Siempre que exista una forma más sencilla de entender el código, se elegirá esa opción antes que una solución más ingeniosa.

La claridad tiene prioridad sobre la complejidad.

---

# Filosofía de desarrollo

El proyecto se desarrolla siguiendo un enfoque incremental.

Cada cambio debe:

- ser pequeño;
- ser fácilmente comprobable;
- no romper funcionalidades existentes;
- quedar terminado antes de comenzar el siguiente.

No se desarrollarán varias funcionalidades complejas simultáneamente.

---

# Desarrollo por etapas

Cada nueva funcionalidad seguirá, siempre que sea posible, este orden:

1. Modelos.
2. Repositories.
3. Services.
4. Schemas.
5. Routers.
6. Templates.
7. JavaScript.
8. Ajustes visuales.

---

# Entrega de código

Cuando un archivo deba modificarse de forma significativa, se entregará completo.

No se utilizarán fragmentos parciales salvo para aclaraciones muy pequeñas.

El objetivo es evitar errores al copiar y pegar.

---

# Convenciones de nombres

## Models

Representan entidades del dominio.

Ejemplos:

Property

Room

Booking

Guest

Platform

---

## Schemas

Todos los schemas finalizarán en:

_schema.py

Ejemplos:

booking_schema.py

guest_schema.py

room_schema.py

De esta forma nunca existirán dudas con los Models.

---

## Services

Todo Service representa reglas del negocio.

Nunca acceso directo a base de datos.

---

## Repositories

Todo Repository encapsula consultas SQLAlchemy.

Nunca contiene reglas de negocio.

---

## Routers

Los Routers únicamente coordinan la petición HTTP.

No implementan reglas del negocio.

No modifican directamente entidades cuando esa lógica pueda residir en un Service.

---

# Responsabilidades

## Model

Representa hechos.

---

## Repository

Obtiene o guarda hechos.

---

## Service

Transforma hechos en comportamiento.

---

## Router

Comunica HTTP con el dominio.

---

## Template

Presenta información.

Nunca contiene reglas de negocio.

---

## JavaScript

Gestiona únicamente el comportamiento de la interfaz.

Nunca implementa reglas de negocio.

---

# Formato del código

Se priorizará:

- nombres descriptivos;
- funciones pequeñas;
- métodos con una única responsabilidad;
- clases sencillas.

---

# Fechas

Todas las fechas visibles para el usuario se mostrarán en formato:

DD-MM-AAAA

La base de datos utilizará el formato nativo correspondiente.

---

# HTML

Todo elemento manipulado desde JavaScript tendrá un identificador único (`id`).

No se dependerá de la posición de un elemento ni de clases CSS para localizarlo.

Ejemplos:

bookingForm

bookingModalTitle

bookingSubmitButton

---

# JavaScript

Toda la lógica relacionada con una funcionalidad deberá agruparse en un único módulo.

Ejemplo:

BookingUI

No se crearán funciones globales.

---

# Reutilización

Si dos funcionalidades comparten una parte importante de su comportamiento, dicha lógica deberá extraerse a un único lugar.

Se evitará duplicar código.

---

# Validaciones

Siempre que sea posible:

- primero se validará en la interfaz;
- posteriormente en el backend.

La validación del backend será siempre la definitiva.

---

# Base de datos

Nunca se accederá directamente desde un Router.

Toda operación deberá pasar por:

Repository

↓

Service

↓

Router

---

# Commits

Cada commit representará una funcionalidad completa o una mejora claramente identificable.

No se mezclarán cambios no relacionados.

---

# Documentación

Toda decisión importante deberá reflejarse en alguno de los documentos del proyecto.

No deberá depender de la memoria de los desarrolladores.

---

# Evolución

Cuando una convención deje de ser adecuada, se modificará este documento antes de comenzar a utilizar la nueva convención.

La documentación siempre tendrá prioridad sobre los hábitos personales de programación.

---

# Regla fundamental

El código debe ser fácil de leer seis meses después de haber sido escrito.

Si una solución dificulta la comprensión del proyecto, deberá replantearse.
