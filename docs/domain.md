# Modelo de Dominio de RentalManager

## Introducción

Este documento define el significado de los conceptos principales de RentalManager.

No describe cómo están implementados técnicamente, sino qué representan dentro del negocio y cómo se relacionan entre sí.

Toda decisión de diseño e implementación deberá respetar este modelo de dominio.

---

# Unidad Reservable

La Unidad Reservable es el elemento central del sistema.

Representa cualquier recurso que pueda ser alquilado durante un periodo de tiempo.

En la versión actual del proyecto se corresponde con una habitación ("Room"), pero el modelo está diseñado para admitir en el futuro otros tipos de unidades, como:

- Apartamentos completos.
- Viviendas.
- Plazas de garaje.
- Trasteros.
- Oficinas.
- Cualquier otro recurso reservable.

Cada Unidad Reservable posee un estado operativo calculado por RentalManager.

---

# Propiedad

Una Propiedad agrupa una o varias Unidades Reservables.

Ejemplos:

- Un piso compartido con cinco habitaciones.
- Un edificio de apartamentos.
- Un conjunto de viviendas.

La Propiedad sirve como elemento organizativo y administrativo.

Cuando una propiedad tenga relaciones o histórico, se conservará mediante archivado o desactivación. No se eliminará físicamente.

---

# Reserva

Una Reserva representa la ocupación conocida de una Unidad Reservable durante un intervalo de tiempo.

Una reserva no implica necesariamente que RentalManager sea el propietario de esa información.

Toda reserva posee una fuente de origen.

No pueden coexistir dos reservas con periodos solapados para una misma Unidad Reservable. RentalManager impedirá su creación o modificación y no ofrecerá una excepción manual a esta regla.

Una reserva manual requiere un huésped. Una reserva importada puede mantener inicialmente un huésped desconocido.

---

# Fuente de autoridad

Toda información gestionada por RentalManager tiene una autoridad.

La autoridad es el sistema responsable de mantener ese dato.

Ejemplos:

- RentalManager (reservas manuales).
- HousingAnywhere.
- Flatio.
- Booking.com.
- Airbnb.

La autoridad determina qué operaciones pueden realizarse sobre una reserva.

Las reservas importadas pertenecen conceptualmente a su plataforma o calendario de origen. RentalManager no las sobrescribe ni cancela de forma arbitraria; cualquier modificación o cancelación externa se tratará según el protocolo de la plataforma correspondiente.

---

# Huésped

El Huésped representa a la persona asociada a una reserva.

Un mismo huésped puede aparecer en distintas reservas.

RentalManager intenta reutilizar la información del huésped siempre que sea posible para evitar duplicidades.

Cuando el origen externo no facilite datos suficientes, el huésped podrá permanecer identificado como desconocido hasta disponer de ellos.

---

# Plataforma

Una Plataforma representa un sistema externo capaz de intercambiar información con RentalManager.

Puede proporcionar:

- Reservas.
- Calendarios.
- Bloqueos.
- Información adicional.

Cada plataforma posee sus propias reglas de funcionamiento.

RentalManager debe adaptarse a ellas.

El catálogo de plataformas es configurable; no está limitado a un conjunto cerrado de proveedores.

---

# Sincronización

La sincronización es el proceso mediante el cual RentalManager actualiza su conocimiento del estado de una Unidad Reservable utilizando información procedente de distintas fuentes.

Sincronizar no significa copiar información.

Significa comparar estados conocidos y actualizar el conocimiento del sistema respetando la autoridad de cada origen.

---

# Conflicto

Un conflicto aparece cuando dos o más fuentes proporcionan información incompatible.

Ejemplos:

- Overbooking.
- Fechas incompatibles.
- Cambios detectados únicamente en una plataforma.
- Reservas desaparecidas de una fuente.

Los conflictos requieren análisis por parte de RentalManager.

No todos implican una acción inmediata.

---

# Incidencia

Una incidencia representa cualquier situación que requiere atención por parte del gestor.

Puede estar originada por:

- Un conflicto.
- Un error de sincronización.
- Una configuración incorrecta.
- Una plataforma inaccesible.
- Cualquier otra situación relevante.

Toda incidencia debe ofrecer al usuario información suficiente para comprender el problema y decidir cómo actuar.

---

# Estado operativo

Cada Unidad Reservable posee un estado operativo.

Ese estado no depende únicamente de las reservas.

Se calcula utilizando toda la información disponible.

Entre otros factores:

- Reservas.
- Bloqueos.
- Sincronizaciones.
- Incidencias.
- Configuración.
- Estado de las plataformas.

El estado operativo representa el conocimiento actual de RentalManager sobre esa unidad.

---

# Estado de confianza

RentalManager asigna un grado de confianza al estado operativo.

Inicialmente se contemplan tres niveles:

- Verificado.
- Pendiente de revisión.
- En conflicto.

Este indicador informa al gestor del grado de fiabilidad de la información mostrada.

---

# Motor de reglas

RentalManager aplica reglas de negocio para interpretar la información recibida.

Su función consiste en:

- Detectar inconsistencias.
- Generar incidencias.
- Calcular estados operativos.
- Ayudar al gestor en la toma de decisiones.

El motor de reglas nunca modifica la autoridad de los datos.

Únicamente interpreta la información disponible.

---

# Relaciones entre conceptos

Propiedad

↓

Unidad Reservable

↓

Estado Operativo

↑

Reservas

↑

Plataformas

↑

Sincronizaciones

↓

Motor de Reglas

↓

Incidencias

↓

Gestor

---

# Principio fundamental

RentalManager no sustituye a las plataformas.

RentalManager observa, interpreta y ayuda a decidir.

La responsabilidad final sobre las decisiones corresponde siempre al gestor.
