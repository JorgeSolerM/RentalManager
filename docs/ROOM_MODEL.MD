# Modelo de Habitación (Room)

Versión: 2.0

---

# Objetivo

La habitación representa la unidad alquilable principal de RentalManager.

Toda reserva, sincronización y calendario maestro estarán asociados a una habitación.

En futuras versiones una habitación podrá representar cualquier unidad alquilable (habitación, estudio, apartamento completo, bungalow, etc.), aunque la interfaz seguirá utilizando el término **Habitación**.

---

# Filosofía

La habitación constituye el núcleo operativo del sistema.

Todo lo que ocurre en RentalManager termina afectando a una habitación.

Las habitaciones pertenecen siempre a una única propiedad.

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

## Código

Código corto utilizado para identificar la habitación.

Ejemplos:

H01

H02

H03

Debe ser único dentro de cada propiedad.

Este código aparecerá en:

- Gantt
- Dashboard
- Búsquedas
- Alertas

---

## Nombre

Campo opcional.

Ejemplos:

Habitación Azul

Suite Norte

Habitación Terraza

Si está vacío, el programa utilizará únicamente el código.

---

## Identificación visible

En el Gantt las habitaciones aparecerán con el formato:

Universidad · H01

Centro · H02

Palmeral · H03

Cada fila será completamente autoexplicativa, independientemente del orden utilizado.

---

## Propiedad

Referencia a la propiedad a la que pertenece.

Una habitación pertenece siempre a una única propiedad.

---

## Activa

Sí / No

Las habitaciones inactivas no aparecerán en el Dashboard ni en el Gantt.

No obstante, conservarán todo su historial.

---

## Orden

Número entero.

Determina el orden manual dentro de la propiedad.

El usuario podrá modificarlo.

---

# Plataformas

Cada habitación podrá estar asociada a una o varias plataformas.

Ejemplos:

- HousingAnywhere
- Booking
- Airbnb
- Flatio
- Spotahome
- Directo
- Manual

Cada plataforma dispondrá de su propia configuración.

---

# Calendarios iCal

## Importación

Una habitación podrá disponer de varios enlaces iCal de importación.

Cada plataforma tendrá su propio enlace.

No existe un límite fijo.

---

## Calendario maestro

Cada habitación tendrá un único calendario maestro.

RentalManager generará automáticamente un enlace iCal permanente.

Este enlace:

- nunca cambiará;
- será el mismo durante toda la vida de la habitación;
- será el enlace que se copiará en todas las plataformas.

El contenido del calendario cambiará continuamente.

La URL nunca.

---

# Reservas

Una habitación podrá contener un número ilimitado de reservas.

Las reservas podrán proceder de:

- Importación iCal
- Creación manual
- Futuras integraciones mediante API

Todas serán tratadas exactamente igual por el sistema.

---

# Información adicional

## Notas

Texto libre.

Uso exclusivamente interno.

---

# Reglas de negocio

- Toda habitación pertenece a una única propiedad.
- Una propiedad puede contener muchas habitaciones.
- El código debe ser único dentro de la propiedad.
- El enlace iCal maestro nunca cambiará.
- Una habitación puede importar varios calendarios.
- Todas las reservas pertenecen siempre a una habitación.

---

# Evolución futura

El modelo queda preparado para incorporar:

- Fotografías.
- Equipamiento.
- Precio.
- Capacidad.
- Estadísticas.
- Ocupación anual.
- Rentabilidad.
- Historial de incidencias.
- Limpiezas programadas.
- Mantenimientos.

Estas funcionalidades no forman parte de la versión 1.0.
