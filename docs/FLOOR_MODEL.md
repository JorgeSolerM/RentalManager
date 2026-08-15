# Modelo de Propiedad (Property)

Versión: 2.0

---

# Objetivo

Una Propiedad representa un inmueble gestionado por RentalManager.

En la interfaz de usuario se utilizará normalmente el término **Piso**, ya que es el caso de uso principal de la aplicación.

Internamente el modelo utilizará el concepto **Property**, permitiendo que en futuras versiones pueda representar otros tipos de inmuebles (apartamentos completos, estudios, chalets, edificios, etc.).

Una propiedad contiene una o varias habitaciones.

---

# Filosofía

La propiedad es el nivel superior de organización de RentalManager.

Toda habitación pertenece siempre a una única propiedad.

Las reservas nunca pertenecen directamente a una propiedad, sino a una habitación.

---

# Datos generales

## Identificador

Tipo:

UUID

Observaciones:

- Identificador interno.
- Invisible para el usuario.
- Nunca cambiará.

---

## Nombre

Nombre completo de la propiedad.

Ejemplos:

Piso Universidad

Piso Centro

Piso Palmeral

Este nombre aparecerá en la ficha de la propiedad.

---

## Nombre corto

Nombre utilizado en aquellas zonas donde el espacio sea limitado.

Ejemplos:

Universidad

Centro

Palmeral

Este nombre será el utilizado en:

- Gantt
- Dashboard
- Búsquedas
- Alertas

---

## Propietario

Nombre del propietario del inmueble.

Ejemplos:

Juan Pérez

María García

HSI Rents

En futuras versiones podrá convertirse en una entidad propia con información adicional.

---

## Dirección

Texto libre.

Ejemplo:

Calle Reina Victoria 24

No aparecerá normalmente en el Dashboard.

---

## Ciudad

Ejemplo:

Elche

---

## Activa

Sí / No

Las propiedades inactivas permanecerán almacenadas, pero no aparecerán en el Dashboard ni en el Gantt por defecto.

Las propiedades con relaciones o histórico se conservarán mediante archivado o desactivación. No se eliminarán físicamente.

---

## Orden

Número entero.

Determina el orden manual de las propiedades dentro de RentalManager.

El usuario podrá modificar este orden.

---

# Información adicional

## Notas

Texto libre.

Uso exclusivamente interno.

---

# Relaciones

Una propiedad contiene una o varias habitaciones.

Una habitación pertenece siempre a una única propiedad.

Una propiedad puede tener uno o varios propietarios en futuras versiones, aunque en la versión 1.0 únicamente existirá un propietario principal.

---

# Reglas de negocio

- Una propiedad con habitaciones, relaciones o histórico no se elimina físicamente; se archiva o desactiva.
- El nombre corto debe ser único dentro de RentalManager.
- El orden será completamente editable por el usuario.
- Toda propiedad debe tener al menos una habitación para poder utilizarse en el motor de sincronización.

---

# Evolución futura

No forma parte de la versión 1.0, pero el modelo queda preparado para incorporar:

- Datos completos del propietario.
- Fotografías del inmueble.
- Documentación.
- Gastos.
- Suministros.
- Estadísticas por propiedad.
- Liquidaciones al propietario.

La arquitectura debe permitir añadir estas funcionalidades sin modificar la estructura principal del modelo.
