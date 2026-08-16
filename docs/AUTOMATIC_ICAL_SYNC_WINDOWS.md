# Sincronización iCal automática en Windows

Este documento prepara la configuración operativa. La aplicación no crea ni
modifica tareas del Programador de tareas automáticamente.

## Requisitos

- Proyecto: `C:\RentalManager`.
- Intérprete: `C:\RentalManager\.venv\Scripts\python.exe`.
- Base de datos y directorio `data` accesibles por la cuenta que ejecuta las
  tareas.
- Variables de entorno necesarias, incluida `PUBLIC_BASE_URL`, disponibles para
  esa cuenta.
- `cloudflared` continúa como servicio Windows existente; no se modifica.

No es necesario abrir el puerto 8000, cambiar el router, firewall o RDP.

## Tarea 1: RentalManager/Uvicorn

Crear posteriormente una tarea denominada, por ejemplo,
`RentalManager Backend`:

- Desencadenador: al iniciar Windows.
- Ejecutar tanto si el usuario inició sesión como si no.
- Programa:
  `C:\RentalManager\.venv\Scripts\python.exe`.
- Argumentos:
  `-m uvicorn backend.main:app --host 127.0.0.1 --port 8000`.
- Directorio inicial: `C:\RentalManager`.
- No iniciar una nueva instancia si ya se está ejecutando.
- Reiniciar la tarea si termina con error.
- No usar `--reload`.

Uvicorn debe seguir escuchando exclusivamente en `127.0.0.1:8000`.

## Tarea 2: sincronización automática

Crear posteriormente una tarea denominada, por ejemplo,
`RentalManager iCal Sync`:

- Desencadenadores: al iniciar Windows y cada 10 minutos indefinidamente.
- Ejecutar tanto si el usuario inició sesión como si no.
- Programa:
  `C:\RentalManager\.venv\Scripts\python.exe`.
- Argumentos: `-m backend.cli.sync_calendars`.
- Directorio inicial: `C:\RentalManager`.
- No iniciar una nueva instancia si la tarea sigue ejecutándose.
- Permitir ejecución manual para diagnóstico.
- No aplicar reintentos adicionales desde Task Scheduler: el CLI gestiona el
  backoff en ciclos posteriores.

El comando procesa secuencialmente los RoomCalendars pendientes. Cada calendario
utiliza una sesión y transacción independientes. Un fallo individual queda
registrado y no impide continuar con los siguientes.

### Códigos de salida

- `0`: ciclo ejecutado; puede contener fallos individuales ya registrados.
- `1`: fallo fatal del ciclo antes de poder completarlo.
- `2`: otro ciclo automático conserva el lock global; no se ejecutó trabajo.

La salida JSON contiene únicamente contadores. Los logs incluyen IDs internos y
códigos de dominio, nunca URLs, tokens, cuerpos de respuesta ni datos del
huésped.

## Locks y recuperación

Los locks se guardan bajo `data/runtime/locks`:

- uno global para el ciclo automático;
- uno por RoomCalendar, compartido con «Sincronizar ahora».

Windows libera el lock cuando termina o cae el proceso. La presencia física del
archivo `.lock` no significa que siga adquirido, por lo que no debe borrarse
manualmente como procedimiento normal de recuperación.

## Diagnóstico posterior

Tras configurar las tareas se deberá comprobar manualmente:

1. arranque sin una sesión interactiva;
2. endpoint local de Uvicorn en `127.0.0.1:8000`;
3. acceso externo exclusivo a `/ical/` mediante el túnel existente;
4. ejecución y código de salida del CLI;
5. actualización de último intento/estado en el workspace;
6. ausencia de dos instancias simultáneas.
