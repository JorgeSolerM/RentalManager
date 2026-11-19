# Corrección y anulación auditada de cobros

Estado actual: candidato R2 validado y desplegado en administración el 20/11/2026. Revisión productiva e45b6d10278c; despliegue R2 exclusivamente de código, sin nuevas migraciones ni movimientos económicos reales. Los apartados de candidato conservan la trazabilidad de las pruebas previas.

## Operación
- Corregir cobro y Anular cobro desde Cuenta económica o historial de asignaciones.
- Motivo obligatorio, preview de cargo/importe/saldo y confirmación explícita.
- Anulación: original void, sin devolución bancaria ficticia. No se elimina el original, sus asignaciones ni su custodia.
- Corrección: original void y sustituto posted, con misma reserva, fecha efectiva, moneda, método, referencia, notas y receptor. El importe nuevo sustituye al anterior, no es un segundo ingreso.
- Si el importe cubre lo asignado se conserva la distribución; la diferencia queda libre. Si es menor, se exige revisión explícita de importes por cargo original. Las nuevas asignaciones a otros cargos se realizan posteriormente mediante el circuito existente.
- Historial PaymentCorrectionOperation: original, sustituto, tipo, motivo, UTC, antes/después, distribución, custodia, fingerprint y clave idempotente. Permite cadenas sucesivas.

## Protecciones
BEGIN IMMEDIATE serializa la validación y toda la escritura en SQLite. Cualquier fallo revierte el conjunto. La huella de preview incluye original, cargos, saldos, asignaciones y custodia. La misma clave/payload devuelve la operación previa; claves reutilizadas con otros datos se rechazan.
Se bloquean cobros no posted/receipt, SEPA, devoluciones vinculadas, correcciones de origen desconocido, liquidaciones consumidas, cargos reservados, reservas/monedas incompatibles y custodia ausente o ambigua. No se admiten sobreasignaciones ni saldo negativo.
La migración añade triggers que impiden editar/borrar auditoría, reactivar/editar originales corregidos y modificar sus asignaciones históricas.
La entrada antigua FinancialService.void_payment delega al servicio auditado y exige motivo.

## Migración
`e45b6d10278c` depende exclusivamente de `d34a5c0f167b`. Añade payment_correction_operations y triggers; sin backfill ni modificación de filas existentes. No tiene dependencia fiscal. No usar stamp ni upgrade heads.
Se ha probado upgrade/downgrade vacío/upgrade sobre copia SQLite consistente de producción, comparando el contenido de todas las tablas previas. Downgrade bloqueado si existe auditoría; el historial nunca se descarta.
Para futuro despliegue autorizado: backup consistente, verificar revisión origen y esquema, upgrade explícito a e45b6d10278c, instalar exclusivamente componentes del manifiesto y comprobar integridad. Antes de revertir, comprobar que no hay nuevas operaciones; no restaurar una copia antigua sobre movimientos posteriores.

## Validación
Pruebas sintéticas de anulación, aumentos/disminuciones, redistribución, custodia manager/owner, idempotencia/concurrencia, rollback, stale preview, SEPA, liquidaciones cerradas, historial, privacidad pública y asignación posterior. Regresión de pagos manuales/devoluciones, liquidaciones y Cuenta económica.
Navegador: 375/768/1280 px; preview, controles y tablas con scroll interno, sin desbordamiento de página ni errores JS. Ninguna acción de pruebas escribe en producción.

## Ejemplos aislados
- http://127.0.0.1:8128/bookings/1/finance : cobro 600 EUR, asignado 200+100; disponible para revisión manual.
- http://127.0.0.1:8128/bookings/2/finance : original 600 EUR sustituido por 250 EUR, asignaciones 150+100; saldo libre cero, cargos pendientes 250+300.

Solo candidato privado en data/runtime/payment-correction-work. Manifest y patch contienen únicamente diferencias del bloque; no publicar BD, logs, demos o copias. Reutilización de inquilinos permanece intacta y separada. Sin cambios en VERI*FACTU.

## Resultados de esta validación
- Batería consolidada: 140 passed (451.59 s), una advertencia de deprecación existente de Starlette/httpx.
- Batería específica final ampliada: 29 passed (73.70 s). Incluye confirmación HTTP e idempotencia, privacidad pública y guards de migración.
- Comando consolidado: `python -m pytest tests/integration/api/test_payment_correction.py tests/audits/test_payment_correction_migration.py tests/integration/api/test_payment_assignment.py tests/audits/test_payment_assignment_migration.py tests/integration/api/test_manual_payments_and_returns.py tests/integration/api/test_sepa_collections.py tests/unit/services/test_financial_service.py tests/unit/test_owner_settlement_service.py tests/integration/api/test_booking_finance_routes.py -q --disable-warnings`.
- Comando específico final: `python -m pytest tests/integration/api/test_payment_correction.py tests/audits/test_payment_correction_migration.py -q --disable-warnings`.
- Copia migrada: quick_check ok, foreign_key_check vacío, hashes de todas las tablas preexistentes iguales antes/después. Producción comprobada exclusivamente en lectura: d34a5c0f167b, integridad correcta y sin tabla payment_correction_operations.
- Sin JavaScript nuevo: interacción mediante formularios y confirmación HTML explícita; navegador real con Playwright/Edge para 375/768/1280 px.

## Candidato R2 — fallo HTTP de anulación
El router anterior accedía directamente a values['amount']; el formulario de anulación no tiene ese campo. También values['reason'] podía causar KeyError ante una petición sin motivo. Ambos casos se corrigen en el router: solo se pasa amount al servicio si kind=replace; el motivo ausente pasa por la validación obligatoria del servicio. La confirmación HTML tampoco envía amount al anular.
No se modifica PaymentCorrectionService ni la lógica económica. El original se obtiene de la BD y se conserva; el importe cero del resultado de anulación ya pertenece a la semántica del servicio, no es una entrada simulada.
Nueva prueba HTTP sobre TCP local con Uvicorn y SQLite temporal: formulario → preview → confirmación sin amount → repetición idempotente → historial/saldos/auditoría. Pruebas de campos omitidos o inválidos, cobro inexistente y bloqueos de custodia, SEPA, devolución y liquidación cerrada.
Producción ya está en e45b6d10278c, con aplicación anterior restaurada. Verificación de esquema e integridad exclusivamente de lectura. El futuro despliegue será solo de código: NO ejecutar upgrade, downgrade, stamp ni migraciones fiscales. Mantener la migración versionable existente sin volver a aplicarla. Conservar backup y rollback de componentes antes de reiniciar exclusivamente administración, cuando se autorice.

Resultado R2: **69 passed**, 155.88 s; una advertencia de deprecación existente Starlette/httpx. Comando: `python -m pytest tests/integration/api/test_payment_correction_http.py tests/integration/api/test_payment_correction.py tests/integration/api/test_payment_assignment.py tests/integration/api/test_booking_finance_routes.py -q --disable-warnings`. Flujo HTTP real local: GET 200, preview 200, confirmación 303 y doble envío 303; un solo cobro original void, cero sustitutos, una operación auditada, saldo cobrado cero y cargos reabiertos. Sin cambios de servicio económico ni migración.

## Despliegue R2 completado
Nueve componentes de ejecución contrastados por hash. Administración y pantallas principales HTTP 200. Anulación HTTP sin amount, confirmación, idempotencia e historial comprobados con el código instalado sobre copia sintética. Auditoría real vacía, hashes de negocio sin cambios e integridad correcta. La web pública e iCal no se reiniciaron. Copias y manifiestos de operación permanecen privados, fuera de Git.
