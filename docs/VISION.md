# RentalManager

## Visión del proyecto

RentalManager es una aplicación diseñada para ayudar a propietarios y gestores de alojamientos a administrar habitaciones y reservas procedentes de múltiples plataformas de alquiler.

No pretende sustituir a dichas plataformas ni convertirse en el origen de toda la información, sino ofrecer una visión unificada, fiable y operativa del estado real de cada alojamiento.

Su objetivo es reducir errores, detectar conflictos y facilitar la toma de decisiones diarias del gestor.

---

# Problema que resuelve

Un mismo alojamiento puede anunciarse simultáneamente en varias plataformas.

Cada una de ellas mantiene su propia información, sus propios calendarios y sus propias reservas.

Además, el gestor puede realizar reservas manuales, bloqueos o modificaciones internas.

Cuando el número de alojamientos aumenta, mantener toda esa información sincronizada se convierte en una tarea compleja y propensa a errores.

RentalManager nace para centralizar esa información y ayudar al gestor a mantener el control.

---

# Qué es RentalManager

RentalManager es el punto central desde el que el gestor puede conocer el estado real de todas sus habitaciones.

No es simplemente un agregador de calendarios.

Su misión consiste en:

- Consolidar información procedente de distintas fuentes.
- Detectar inconsistencias entre ellas.
- Mostrar el estado operativo de cada habitación.
- Ayudar al usuario a resolver conflictos.
- Mantener un histórico fiable de la actividad.

---

# Qué NO pretende hacer

RentalManager no pretende sustituir los sistemas de gestión propios de plataformas como HousingAnywhere, Flatio, Airbnb o Booking.

Tampoco pretende convertirse en la autoridad de información cuya propiedad pertenece a otros sistemas.

Su función consiste en observar, integrar y asistir.

---

# Principios fundamentales

## 1. La autoridad pertenece al origen del dato

Todo dato tiene un sistema de origen.

Ese sistema es el propietario de dicho dato.

Por ejemplo:

- Una reserva creada manualmente pertenece a RentalManager.
- Una reserva importada desde HousingAnywhere pertenece a HousingAnywhere.
- Una reserva importada desde Flatio pertenece a Flatio.

RentalManager respetará siempre esa autoridad.

---

## 2. Nunca se contradice una fuente externa

Si una plataforma considera una habitación ocupada, RentalManager nunca la considerará libre simplemente porque el usuario modifique la información localmente.

La aplicación informará del conflicto y propondrá la acción adecuada, pero no inventará una realidad distinta.

---

## 3. Las incidencias son información, no errores

Una incidencia no significa necesariamente que exista un fallo.

Significa que existe una situación que requiere atención por parte del gestor.

Por ejemplo:

- Overbooking.
- Información contradictoria entre plataformas.
- Sincronización incompleta.
- Reserva modificada en el origen.

Las incidencias forman parte del funcionamiento normal del sistema.

---

## 4. El objetivo es ayudar al gestor

RentalManager no toma decisiones por el usuario.

Su función consiste en:

- Detectar situaciones relevantes.
- Explicarlas de forma clara.
- Indicar sus consecuencias.
- Recomendar la acción más adecuada.

La decisión final siempre pertenece al gestor.

---

# Habitación como elemento central

La entidad más importante del sistema no es la reserva.

Es la habitación.

Cada habitación posee un estado operativo que depende de múltiples factores:

- Reservas.
- Bloqueos.
- Sincronizaciones.
- Incidencias.
- Configuración.
- Estado de las plataformas.

Las reservas representan únicamente una parte de ese estado.

---

# Estado operativo

RentalManager mantiene para cada habitación una representación del estado conocido en cada momento.

Ese estado se calcula utilizando toda la información disponible.

No depende exclusivamente de una única plataforma.

---

# Confianza de la información

No toda la información posee el mismo grado de fiabilidad.

El sistema deberá ser capaz de indicar cuándo el estado de una habitación puede considerarse:

- Verificado.
- Pendiente de revisión.
- En conflicto.

El objetivo es que el gestor conozca siempre el grado de confianza que puede depositar en la información mostrada.

---

# Filosofía de diseño

Cada funcionalidad que se incorpore a RentalManager deberá responder afirmativamente a estas preguntas:

- ¿Ayuda al gestor a comprender mejor el estado de sus alojamientos?
- ¿Reduce el riesgo de errores?
- ¿Respeta la autoridad de los datos?
- ¿Facilita la resolución de conflictos?
- ¿Hace el trabajo diario más sencillo?

Si la respuesta es negativa, probablemente esa funcionalidad no pertenezca a RentalManager.

---

# Misión

RentalManager centraliza la información procedente de múltiples plataformas de alquiler, identifica inconsistencias entre ellas y proporciona al gestor una visión fiable del estado operativo de sus alojamientos, respetando siempre la autoridad de cada fuente de datos y ayudándole a tomar decisiones con seguridad.
