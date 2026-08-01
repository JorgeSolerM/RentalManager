# Diseño funcional del Gantt

Versión: 2.0

---

# Objetivo

El Gantt constituye el centro de operaciones de RentalManager.

Desde esta pantalla el usuario gestionará el trabajo diario relacionado con las reservas, manteniendo siempre una visión global de todas las habitaciones.

El objetivo principal es minimizar el número de clics y reducir la necesidad de desplazamiento vertical.

---

# Filosofía

El Gantt no es simplemente un calendario.

Es una herramienta de trabajo.

Su misión es permitir localizar cualquier reserva en pocos segundos y realizar las operaciones habituales con el mínimo esfuerzo.

---

# Distribución general

+-------------------------------------------------------------------------------------------------------------+
| Barra superior                                                                                              |
+------------------------------+------------------------------------------------------------------------------+
|                              |                                                                              |
| Lista de propiedades         |                         Diagrama de Gantt                                    |
| y habitaciones               |                                                                              |
|                              |                                                                              |
|                              |                                                                              |
+------------------------------+------------------------------------------------------------------------------+
| Panel inferior de información (visible únicamente cuando existe una reserva seleccionada)                  |
+-------------------------------------------------------------------------------------------------------------+

---

# Barra superior

Contendrá:

- Botón "Hoy"
- Semana anterior
- Semana siguiente
- Selector de fecha
- Selector de escala temporal
- Búsqueda
- Botón de sincronización
- Acceso a configuración

---

# Panel izquierdo

Mostrará todas las habitaciones.

Cada fila será completamente autoexplicativa.

Formato:

Nombre corto de la propiedad · Código de habitación

Ejemplos:

Universidad · H01

Universidad · H02

Centro · H01

Palmeral · H03

No será necesario consultar otras filas para conocer la propiedad a la que pertenece una habitación.

---

# Panel derecho

Mostrará el diagrama temporal.

Cada línea representará una única habitación.

Cada bloque representará una única reserva.

---

# Contenido de una reserva

El texto aparecerá siempre dentro del bloque.

Formato:

Nombre del inquilino · Canal

Ejemplos:

John Smith · Flatio

Laura Pérez · HousingAnywhere

María López · Booking

Si el espacio disponible no fuese suficiente, el texto se truncará automáticamente.

Nunca aparecerá fuera del bloque.

---

# Información visible

El Gantt mostrará únicamente la información necesaria para identificar una reserva.

El resto de información aparecerá en el panel inferior.

---

# Panel inferior

Aparecerá únicamente cuando exista una reserva seleccionada.

Mostrará:

- Nombre del inquilino
- Propiedad
- Habitación
- Fecha de entrada
- Fecha de salida
- Duración
- Canal
- Estado
- Notas
- Información de sincronización

El objetivo es evitar abrir ventanas para consultar información básica.

---

# Escala temporal

El usuario podrá seleccionar:

- Semana
- Dos semanas
- Mes
- Tres meses
- Año

La aplicación abrirá siempre centrada en la fecha actual.

---

# Altura de filas

La aplicación utilizará por defecto el modo:

Compacto

La prioridad será mostrar el mayor número posible de habitaciones en pantalla.

La altura podrá configurarse desde las preferencias.

---

# Navegación

La aplicación abrirá siempre en un estado conocido.

Configuración inicial:

- Fecha actual
- Vista mensual
- Filas compactas
- Sin filtros
- Ninguna reserva seleccionada

---

# Colores

Los colores nunca serán la única fuente de información.

Toda información importante deberá aparecer también mediante texto o iconos.

Los colores tendrán únicamente un papel de apoyo visual.

---

# Dashboard y Gantt

Ambas pantallas tienen funciones distintas.

Dashboard

Responderá a la pregunta:

¿Qué tengo que hacer hoy?

Gantt

Responderá a la pregunta:

¿Dónde ocurre cada reserva y cómo puedo gestionarla?

---

# Principios de diseño

Toda reserva deberá responder inmediatamente a cuatro preguntas:

¿Cuándo?

¿Qué ocurre?

¿Con quién?

¿Dónde?

---

Toda fila deberá ser completamente autoexplicativa.

---

El usuario nunca deberá depender del color para comprender la información.

---

La claridad tendrá prioridad sobre la estética.

---

El espacio vertical es un recurso valioso.

La aplicación minimizará el desplazamiento vertical.

---

La información importante deberá estar visible.

La información secundaria deberá encontrarse a un único clic.

---

El Gantt constituye el centro de operaciones de RentalManager.
