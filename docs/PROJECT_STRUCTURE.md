# RentalManager
## Estructura del proyecto

Versión del documento: 2.0

Última actualización: 01/08/2026

---

# Filosofía del proyecto

RentalManager se desarrolla siguiendo los siguientes principios:

- KISS (Keep It Simple).
- Una única responsabilidad por archivo.
- Una única responsabilidad por carpeta.
- El código debe ser fácil de entender antes que ingenioso.
- Se evita duplicar código.
- Antes de añadir una funcionalidad nueva se estudia si realmente aporta valor.
- La seguridad del dato tiene prioridad sobre la velocidad.
- La experiencia diaria del usuario prevalece sobre la estética.

---

# Objetivo del proyecto

RentalManager no es únicamente un agregador de calendarios iCal.

Es un centro de operaciones para la gestión de alquileres por habitaciones.

Su objetivo principal es:

- sincronizar calendarios de múltiples plataformas;
- generar un calendario maestro permanente para cada habitación;
- facilitar la gestión diaria de entradas y salidas;
- reducir el tiempo empleado en tareas repetitivas;
- minimizar los errores humanos.

---

# Estructura del proyecto

RentalManager/

    backend/
    data/
    docs/
    tests/

---

# backend/

Contiene todo el código fuente de la aplicación.

Nunca almacenará información del usuario.

---

## backend/api/

Routers de FastAPI.

Cada router representa un módulo funcional.

Ejemplos:

- dashboard.py
- gantt.py
- properties.py
- settings.py

Su única responsabilidad es recibir peticiones y devolver respuestas.

Nunca contendrán lógica de negocio.

---

## backend/core/

Componentes compartidos.

Ejemplos futuros:

- configuración
- constantes
- logging
- utilidades
- seguridad

---

## backend/database/

Todo lo relacionado con la persistencia.

Ejemplos:

- SQLite
- conexión
- sesiones
- migraciones

---

## backend/models/

Modelos de datos.

En versiones futuras podrán dividirse en:

- database
- schemas

---

## backend/repositories/

Acceso a los datos.

Su misión será:

- leer
- guardar
- actualizar
- eliminar

Nunca contendrán reglas de negocio.

---

## backend/services/

Aquí vivirá el verdadero funcionamiento de RentalManager.

Ejemplos:

- motor de sincronización iCal
- generación del calendario maestro
- resolución de conflictos
- importación de plataformas
- validaciones
- reglas de negocio

Es el núcleo de la aplicación.

---

## backend/static/

Recursos estáticos.

Actualmente:

- css/

En el futuro:

- js/
- images/
- icons/

Nunca contendrá datos del usuario.

---

## backend/templates/

Plantillas HTML.

Se divide en:

### components/

Elementos reutilizables.

Ejemplos:

- header
- sidebar
- footer

---

### layouts/

Plantillas base.

Actualmente:

- base.html

Todas las páginas heredarán de ella.

---

### pages/

Páginas completas.

Actualmente:

- dashboard
- gantt
- properties
- settings

---

# data/

Datos generados por la aplicación.

Ejemplos:

- base de datos SQLite
- copias de seguridad
- archivos temporales
- exportaciones

Nunca contendrá código.

---

# docs/

Documentación oficial del proyecto.

Ejemplos:

- visión del proyecto
- modelos de datos
- arquitectura
- casos de uso
- decisiones de diseño

La documentación tendrá el mismo nivel de importancia que el código.

---

# tests/

Pruebas automáticas.

Cada nueva funcionalidad importante deberá poder validarse mediante pruebas.

---

# Arquitectura general

RentalManager se organiza en torno a cinco entidades principales.

Property

↓

Room

↓

Platform

↓

Booking

↓

Synchronization Engine

El motor de sincronización permanece desacoplado del modelo de datos.

Esto permitirá incorporar futuras APIs sin modificar la arquitectura principal.

---

# Convenciones

## Idioma

Código:

Inglés.

Comentarios:

Español.

Interfaz:

Español.

Documentación:

Español.

---

## Nombres

Archivos:

snake_case

Variables:

snake_case

Clases:

PascalCase

---

## Organización

Antes de crear una carpeta nueva debe comprobarse si ya existe otra con la misma responsabilidad.

La simplicidad siempre tendrá prioridad.

---

# MVP (Versión 1.0)

La primera versión deberá permitir:

- Crear propiedades.
- Crear habitaciones.
- Configurar plataformas.
- Importar calendarios iCal.
- Generar un calendario maestro permanente.
- Visualizar las reservas mediante un Gantt.
- Crear reservas manuales.
- Consultar un Dashboard operativo.
- Sincronizar calendarios.

Todo aquello que no sea imprescindible para alcanzar estos objetivos quedará planificado para versiones posteriores.

---

# Principio fundamental

Cada nueva funcionalidad deberá cumplir al menos una de estas condiciones:

- ahorrar tiempo al usuario;
- reducir el riesgo de cometer errores.

Si no cumple ninguna de ellas, deberá replantearse su incorporación al proyecto.
