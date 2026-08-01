# RentalManager
# Visión del Proyecto

Versión: 1.0

---

# ¿Qué es RentalManager?

RentalManager es una aplicación de escritorio diseñada para gestionar alquileres por habitaciones de forma sencilla, rápida y segura.

Su objetivo principal es unificar la información procedente de distintas plataformas de alquiler mediante calendarios iCal y convertirla en una herramienta de gestión diaria.

RentalManager no pretende ser únicamente un agregador de calendarios.

Pretende convertirse en el centro de operaciones del negocio.

---

# Objetivo principal

Reducir el tiempo dedicado a la gestión diaria de los alquileres.

Cada nueva funcionalidad deberá cumplir al menos uno de estos objetivos:

- ahorrar tiempo;
- reducir errores;
- mejorar la información disponible para tomar decisiones.

---

# Filosofía

RentalManager se desarrolla siguiendo los siguientes principios.

---

## 1. Keep It Simple (KISS)

La solución más sencilla será siempre la preferida.

Solo se añadirá complejidad cuando aporte un beneficio claro.

---

## 2. Seguridad antes que velocidad

Las acciones que puedan provocar errores importantes requerirán confirmación.

Ejemplo:

Las fechas de una reserva nunca podrán modificarse arrastrando la barra del Gantt.

---

## 3. La información importante debe estar visible

El usuario no debería abrir ventanas para conocer la información básica.

Cada reserva debe responder inmediatamente a cuatro preguntas:

- ¿Cuándo?
- ¿Qué ocurre?
- ¿Con quién?
- ¿Dónde?

---

## 4. El color nunca será la única fuente de información

Toda información importante aparecerá también mediante texto o iconos.

Los colores únicamente servirán como apoyo visual.

---

## 5. El espacio vertical es un recurso valioso

El Gantt debe mostrar el mayor número posible de habitaciones.

Se minimizará el desplazamiento vertical.

---

## 6. El Dashboard y el Gantt tienen funciones distintas

Dashboard:

¿Qué tengo que hacer?

Gantt:

¿Dónde ocurre y cómo lo gestiono?

---

## 7. Los datos introducidos manualmente tienen prioridad

La información editada por el usuario nunca será sobrescrita automáticamente por una sincronización sin su consentimiento.

---

## 8. El programa siempre comenzará en un estado conocido

Al iniciar RentalManager:

- Dashboard operativo.
- Gantt centrado en hoy.
- Vista mensual.
- Filas compactas.
- Sin filtros.
- Ninguna reserva seleccionada.

---

## 9. Cada fila del Gantt será autoexplicativa

Nunca dependerá del contexto.

Formato recomendado:

Universidad · H01

Centro · H02

Palmeral · H03

---

## 10. El calendario es un medio, no un fin

El verdadero objetivo del programa es facilitar la gestión diaria del negocio.

---

# Qué NO pretende ser RentalManager

RentalManager no pretende competir con grandes PMS.

No pretende gestionar contabilidad.

No pretende sustituir un CRM.

No pretende incorporar funcionalidades que no aporten valor al trabajo diario.

---

# Público objetivo

Inicialmente:

Propietarios y gestores de alquileres por habitaciones.

La arquitectura permitirá evolucionar hacia otros modelos de alquiler.

---

# Principio fundamental

Antes de incorporar una nueva funcionalidad deberá responderse una pregunta:

"¿Esta funcionalidad ahorra tiempo o reduce errores?"

Si la respuesta es negativa, probablemente no deba incorporarse.

---

# Nuestra prioridad

Construir una herramienta rápida, clara, fiable y agradable de utilizar durante muchas horas al día.

La productividad del usuario siempre tendrá prioridad sobre la complejidad técnica.
