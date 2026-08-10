# Roadmap de RentalManager

## Objetivo

Este documento define la evolución prevista del proyecto.

No representa un compromiso inamovible.

Su finalidad es ayudar a priorizar el desarrollo y mantener el foco en las funcionalidades que aportan mayor valor al gestor.

---

# Estados

Cada funcionalidad utilizará uno de los siguientes estados:

✅ Completado

🚧 En desarrollo

📋 Planificado

💡 Idea futura

---

# Módulo 1 — Núcleo

## Propiedades

✅ Gestión de propiedades

✅ Alta

✅ Edición

---

## Habitaciones

✅ Gestión de habitaciones

✅ Workspace de habitación

✅ Estado actual

📋 Fotografía principal

📋 Configuración

---

## Reservas

✅ Crear reserva

✅ Editar reserva

🚧 Cancelación / eliminación (según modelo de autoridad)

📋 Validaciones de interfaz

📋 Mensajes de confirmación

📋 Historial de cambios

---

## Huéspedes

✅ Creación automática

✅ Reutilización

📋 Ficha completa

📋 Búsqueda avanzada

---

# Módulo 2 — Plataformas

📋 Gestión de plataformas

📋 Iconos

📋 Configuración

📋 Credenciales

📋 Estado de conexión

---

# Módulo 3 — Sincronización

📋 Importación iCal

📋 Exportación iCal

📋 Sincronización manual

📋 Sincronización automática

📋 Comparación de cambios

📋 Historial de sincronizaciones

📋 Registro de errores

---

# Módulo 4 — Motor de reglas

📋 Estado operativo

📋 Detección de overbooking

📋 Conflictos entre plataformas

📋 Conflictos manuales

📋 Recomendaciones automáticas

📋 Cálculo de confianza

---

# Módulo 5 — Incidencias

📋 Lista global

📋 Incidencias por habitación

📋 Resolución

📋 Historial

📋 Seguimiento

---

# Módulo 6 — Dashboard

📋 Estado general

📋 Indicadores

📋 Próximas entradas

📋 Próximas salidas

📋 Alertas

📋 Actividad reciente

---

# Módulo 7 — Calendario

📋 Vista mensual

📋 Vista Gantt

📋 Filtros

📋 Colores por plataforma

📋 Colores por estado

📋 Navegación rápida

---

# Módulo 8 — Gestión documental

📋 Fotografías

📋 Contratos

📋 Inventarios

📋 Documentación

---

# Módulo 9 — Estadísticas

📋 Ocupación

📋 Ingresos

📋 Duración media

📋 Plataformas

📋 Rentabilidad

---

# Módulo 10 — Automatizaciones

💡 Avisos

💡 Limpiezas

💡 Recordatorios

💡 Revisiones

💡 Informes periódicos

---

# Módulo 11 — API

💡 API pública

💡 Webhooks

💡 Integraciones externas

---

# Prioridad actual

La prioridad inmediata del proyecto será completar el núcleo funcional antes de desarrollar módulos avanzados.

Orden previsto:

1. Finalizar el módulo de Reservas.

2. Diseñar e implementar la sincronización iCal.

3. Construir el motor de reglas.

4. Implementar el sistema de incidencias.

5. Desarrollar el Dashboard basado en el estado operativo.

Todo nuevo desarrollo deberá contribuir al avance de estos objetivos.

---

# Funcionalidades diferenciales

RentalManager pretende diferenciarse de otros gestores mediante:

- Respeto de la autoridad de los datos.

- Estado operativo calculado.

- Detección automática de conflictos.

- Recomendación de acciones.

- Gestión centralizada de múltiples plataformas.

Estas funcionalidades tendrán siempre prioridad frente a mejoras únicamente estéticas.

---

# Regla de planificación

Antes de comenzar un nuevo desarrollo deberá comprobarse:

- que la funcionalidad pertenece al Roadmap;

- que su prioridad es adecuada;

- que no contradice la Visión, el Dominio ni la Arquitectura del proyecto.

El Roadmap será revisado y actualizado al finalizar cada sprint importante.
