# Arquitectura de RentalManager

## Objetivo

Este documento describe la arquitectura técnica de RentalManager y los principios que guían su implementación.

No pretende documentar una tecnología concreta, sino definir cómo se organizan las responsabilidades dentro del sistema para facilitar su evolución y mantenimiento.

Toda nueva funcionalidad deberá integrarse respetando esta arquitectura.

---

# Principios generales

La arquitectura de RentalManager se basa en cinco principios fundamentales:

- Separación de responsabilidades.
- Dominio independiente de la tecnología.
- Reutilización de la lógica de negocio.
- Baja dependencia entre módulos.
- Evolución progresiva sin romper funcionalidades existentes.

---

# Arquitectura por capas

RentalManager se organiza en cuatro grandes capas.

```
Usuario
        │
        ▼
Presentación
        │
        ▼
Aplicación
        │
        ▼
Dominio
        │
        ▼
Persistencia
```

Cada capa posee una responsabilidad claramente definida.

---

# Capa de Presentación

Responsable de la interacción con el usuario.

Incluye:

- Templates Jinja2.
- Bootstrap.
- JavaScript.
- CSS.
- Recursos estáticos.

Su misión consiste únicamente en mostrar información y recoger acciones del usuario.

Nunca contiene reglas de negocio.

---

# Capa de Aplicación

Coordina las operaciones solicitadas por el usuario.

Está formada principalmente por:

- Routers FastAPI.

Su responsabilidad consiste en:

- recibir peticiones;
- validar datos de entrada;
- invocar los servicios adecuados;
- devolver la respuesta.

Los routers nunca implementan lógica de negocio.

---

# Capa de Dominio

Es el núcleo de RentalManager.

Contiene las reglas que describen el funcionamiento del negocio.

Incluye:

- Services.
- Reglas de validación.
- Reglas de sincronización.
- Cálculo del estado operativo.
- Generación de incidencias.

El dominio debe poder evolucionar independientemente de la interfaz de usuario.

---

# Capa de Persistencia

Responsable del acceso a los datos.

Incluye:

- Models SQLAlchemy.
- Repositories.
- Base de datos.

Los modelos representan hechos.

Los repositorios encapsulan el acceso a dichos hechos.

Nunca contienen reglas de negocio.

---

# Flujo de una petición

Cuando un usuario realiza una acción:

```
Usuario

↓

Router

↓

Service

↓

Repository

↓

Base de datos
```

La respuesta sigue el camino inverso.

---

# Flujo de sincronización

Las sincronizaciones constituyen un flujo independiente.

```
Plataformas

↓

Importadores

↓

Dominio

↓

Motor de reglas

↓

Incidencias

↓

Estado operativo
```

El usuario no interviene directamente en este proceso.

---

# Motor de reglas

El motor de reglas interpreta la información almacenada.

Su responsabilidad consiste en:

- detectar inconsistencias;
- calcular estados operativos;
- generar incidencias;
- ayudar al gestor a tomar decisiones.

No modifica la autoridad de los datos.

---

# Estado operativo

El estado operativo representa el conocimiento actual que posee RentalManager sobre una Unidad Reservable.

No es un dato introducido manualmente.

Se obtiene aplicando reglas sobre:

- reservas;
- bloqueos;
- sincronizaciones;
- incidencias;
- configuración;
- plataformas.

Toda la interfaz deberá construirse alrededor del estado operativo.

---

# Hechos y conocimiento

La arquitectura distingue claramente dos conceptos.

## Hechos

Representan información almacenada.

Ejemplos:

- una reserva;
- una habitación;
- un huésped;
- una plataforma.

Los hechos describen la realidad conocida.

---

## Conocimiento

Representa conclusiones obtenidas a partir de los hechos.

Ejemplos:

- una habitación está disponible;
- existe un overbooking;
- una sincronización ha fallado;
- el estado es fiable.

El conocimiento siempre es calculado.

Nunca debe confundirse con los hechos almacenados.

---

# Responsabilidad de cada componente

## Models

Representan hechos del dominio.

No contienen reglas de negocio.

---

## Repositories

Gestionan el acceso a la base de datos.

No conocen la interfaz de usuario.

No contienen reglas de negocio.

---

## Services

Implementan las reglas del negocio.

Son el lugar donde debe residir toda la lógica funcional del sistema.

---

## Schemas

Representan los datos intercambiados entre el backend y el exterior.

No contienen lógica de negocio.

---

## Routers

Traducen peticiones HTTP en llamadas a los servicios.

No modifican directamente las entidades del dominio.

---

## Templates

Presentan la información.

Nunca contienen reglas de negocio.

---

## JavaScript

Gestiona el comportamiento dinámico de la interfaz.

Nunca implementa decisiones de negocio.

---

# Dependencias permitidas

La dirección de las dependencias será siempre descendente.

```
Presentación

↓

Aplicación

↓

Dominio

↓

Persistencia
```

Nunca en sentido contrario.

---

# Evolución prevista

La arquitectura está preparada para incorporar nuevos módulos sin alterar los existentes.

Entre ellos:

- Motor de sincronización.
- Gestión documental.
- Fotografías.
- Estadísticas.
- Informes.
- Automatizaciones.
- API pública.

Todos deberán respetar los mismos principios arquitectónicos.

---

# Regla fundamental

Las entidades almacenan hechos.

Los servicios generan conocimiento.

Toda funcionalidad nueva deberá respetar esta separación.
