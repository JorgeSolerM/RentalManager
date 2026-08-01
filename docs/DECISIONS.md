# Registro de decisiones

---

## DEC-001

Fecha: 01/08/2026

Todas las claves primarias utilizarán INTEGER AUTOINCREMENT.

Motivo:

La aplicación utiliza SQLite local.

UUID no aporta ventajas en la versión 1.x.

---

## DEC-002

El calendario maestro tendrá una URL permanente.

Nunca cambiará.

Solo cambiará su contenido.

---

## DEC-003

No existe el concepto "Channel".

Toda reserva pertenece a una Platform.

---

## DEC-004

Las fechas nunca podrán modificarse arrastrando una reserva.

Siempre se utilizará un selector de fechas.

---

## DEC-005

RentalManager siempre abrirá en un estado conocido.

No recuperará la sesión anterior.

---

## DEC-006

El Gantt utilizará filas compactas por defecto.

El espacio vertical tiene prioridad.

---

## DEC-007

Cada fila del Gantt será autoexplicativa.

Formato:

Nombre corto de la propiedad · Código de habitación.

Ejemplo:

Universidad · H01
