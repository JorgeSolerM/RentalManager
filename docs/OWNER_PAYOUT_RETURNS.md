# Devoluciones bancarias recibidas de pagos a propietarios — fase 1

Estado: fase 1 desplegada y validada técnicamente el 20/11/2026, sin crear movimientos económicos reales. La revisión manual conjunta queda para el final del circuito económico; no bloquea este cierre. No realiza operaciones bancarias.

## Alcance

Registra únicamente dinero efectivamente abonado por el banco, correspondiente a una transferencia destinada correctamente al propietario. No incluye pagos a beneficiarios incorrectos, duplicados bancarios reales, recuperaciones pendientes ni regularizaciones excepcionales.

`OwnerPayout` y sus triggers permanecen inmutables. `OwnerPayoutReturn` conserva la relación con el registro vigente y la raíz de su cadena de sustituciones, importe, fecha efectiva, referencia, motivo, identificador bancario opcional, operador de sesión cuando exista, fecha UTC, huellas y clave de idempotencia. La cuenta receptora se identifica con IBAN en el formulario privado; se guarda únicamente su SHA-256 y últimos cuatro caracteres. No se obtiene ni se verifica un extracto bancario automáticamente.

## Saldos

El servicio común distingue pagos vigentes brutos, devoluciones recibidas, pagado neto, pendiente y fondos disponibles del propietario. Una liquidación de 500 EUR con pago de 500 EUR y devolución de 200 EUR queda cerrada económicamente, pagada neta por 300 EUR y pendiente por 200 EUR. Solo vuelven a estar disponibles los 200 EUR recibidos. No se crea automáticamente otro payout y no se atribuyen fondos a otros propietarios.

Los originales sustituidos no computan. Una URL histórica resuelve el registro vigente de la misma transferencia. Una cadena anulada administrativamente no admite devoluciones. Después de registrar una devolución se bloquean las correcciones administrativas de esa transferencia. Se conservan los bloqueos existentes de compensaciones.

## Duplicados y concurrencia

- BEGIN IMMEDIATE antes de revalidar, insertar y recalcular; transacción única con rollback.
- Misma clave de petición y contenido: devuelve el mismo registro; contenido diferente: rechazo.
- Identificador bancario, normalizado, junto con la huella de la cuenta receptora: clave única aunque cambie la petición, importe o fecha.
- Sin identificador fiable: coincidencia de transferencia, fecha e importe bloqueada conservadoramente. Cambiar solo la referencia no elude el control.
- Dos abonos realmente distintos de igual fecha e importe necesitan identificadores bancarios verificables distintos para distinguirlos. No se ofrece un override silencioso.
- La aplicación no puede detectar un duplicado si se falsean todos los datos bancarios. La declaración de recepción efectiva y contraste con el banco siguen siendo obligatorios.
- La huella del preview incluye pagos, correcciones, devoluciones y cierres del propietario; cambios concurrentes exigen revisar de nuevo.

## Interfaz y documentos

En Liquidación → Pagos al propietario: Registrar devolución bancaria / Ver devoluciones. Se exige motivo, referencia, fecha efectiva, cuenta receptora y declaración expresa de abono recibido. Revisar devolución muestra máximos, pagado neto, pendiente y fondos antes/después. La confirmación requiere nuevamente la declaración y aceptación del impacto, sin casillas preactivadas.

Las liquidaciones, consumos y PDF históricos no se reescriben. Solo una nueva generación documental solicitada crea otra versión con pagos, devoluciones recibidas y pendiente actuales.

Los endpoints pertenecen exclusivamente a administración; no se registran en la aplicación pública. Respuestas del formulario: private, no-store.

## Migración, despliegue y reversión

Migración aditiva `178e9035abf0`, exclusivamente dependiente de `067d8f3249ae`. Crea la tabla y sus índices, restricciones y triggers nuevos de inmutabilidad/coherencia, además de bloquear auditorías administrativas incompatibles. No altera los triggers existentes de OwnerPayout ni requiere la rama fiscal.

Validar sobre copia consistente con DATABASE_URL explícita y ALEMBIC_REQUIRE_TEMPORARY_DATABASE=1. El candidato ha probado upgrade, downgrade vacío y upgrade; downgrade se niega a eliminar devoluciones existentes. No usar stamp ni upgrade heads. El entorno navegable se ha sembrado desde metadatos con datos exclusivamente sintéticos; la prueba de migración usa una copia consistente separada.

El despliegue autorizado aplicó únicamente 178e9035abf0 sobre 067d8f3249ae, después de una copia consistente. Se instalaron diez componentes de administración y la migración. Solo se reinició administración; la web pública e iCal permanecieron intactos. La tabla de devoluciones quedó vacía y la integridad fue correcta. Ante reversión, no cargar código antiguo sobre devoluciones nuevas: ignoraría los abonos al calcular los saldos. Con datos nuevos debe mantenerse lectura compatible y evaluarse una corrección hacia delante; no eliminar el historial ni restaurar una BD que perdería movimientos.

## Validación

Pruebas unitarias de importes, cadenas, límites, duplicados, copropiedad, fondos compartidos, declaraciones, idempotencia, concurrencia, rollback, stale preview, privacidad y documentos históricos. Pruebas HTTP con servidor real y campos ausentes; regresión de correcciones administrativas, liquidaciones y gastos. Migración y preservación de triggers. Validación visual 375/768/1280 sin overflow ni errores JavaScript; sin confirmar nuevos movimientos en el entorno de revisión manual.

Resultados exactos y manifiesto se entregan junto al candidato. No se han probado transferencias reales, conciliación automática bancaria ni escenarios de fases posteriores.


## Revisión manual del candidato

Solo en `http://127.0.0.1:8131`, nunca en producción. Los formularios no traen la confirmación marcada. Para probar puede emplearse la cuenta sintética `ES9121000418450200051332`, recepción `2026-09-22`, un motivo y una referencia de prueba. El identificador único debe ser el del abono simulado, no una cadena inventada para eludir un aviso de duplicado real.

1. `/settlements/1/payouts/1/returns`: pago 500 EUR; revisar devolución íntegra de 500 EUR. Nuevo pagado neto 0, pendiente 500.
2. `/settlements/2/payouts/2/returns`: pago 500 EUR; revisar devolución parcial de 200 EUR. Nuevo pagado neto 300, pendiente 200.
3. `/settlements/3/payouts/3/returns`: ya recibió 200 EUR; revisar otros 100 EUR. Total devuelto 300, pagado neto 200, pendiente 300. El abono previo tiene identificador `SYNTHETIC-3-1`.
4. `/settlements/4/payouts/4/returns`: devolución total ya registrada, bloquea otro abono. Para comprobar duplicados, en escenario 3 introducir de nuevo 200 EUR, misma fecha e identificador `SYNTHETIC-3-1`; debe rechazarse antes de confirmar.
5. `/settlements/5/payouts/5/returns`: cadena de sustitución 500 → 450 EUR y dos devoluciones de 150 y 100 EUR. Raíz única, pagado neto 200 EUR y pendiente 300 EUR, con los movimientos originales conservados.

Las cuatro devoluciones preexistentes pertenecen exclusivamente a los escenarios sintéticos 3–5. La comprobación visual automática solo abrió formularios y previews; no confirmó nuevas devoluciones en este entorno manual.
