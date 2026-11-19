# Corrección de gastos y anulación administrativa de pagos

Estado: candidato aislado, pendiente de validación manual y autorización de despliegue. No aplicado a producción.

## Circuito

La ficha de gasto permite corregir base/importe, concepto y categoría conservando el identificador. IVA y retención existentes se conservan; el preview muestra el total calculado. El total no puede quedar por debajo del pagado efectivo. Referencias, proveedor, finca, propietario y justificantes existentes no se modifican.

Anular un pago exige motivo y declaración explícita de que no hubo salida real de dinero, tanto al revisar como al confirmar. La aplicación no puede comprobar por sí sola esa declaración frente al banco. Si hubo salida real, debe usarse una devolución real o regularización, nunca esta operación administrativa.

El pago conserva importe, fecha, receptor, método, referencias y notas. Solo cambian lifecycle posted→void y voided_at. Una auditoría inmutable conserva antes/después, impacto, motivo, fecha UTC, huella de revisión e idempotencia. No se crea pago, devolución ni sustituto. Los pagos void no participan en saldos ni futuras liquidaciones ni admiten devoluciones nuevas.

El gasto solo se anula cuando no tiene pagos efectivos y cada pago anulado dispone de auditoría íntegra. Cualquier devolución vinculada bloquea la operación aunque el saldo neto sea cero. Los consumos de cualquier copropietario bloquean cambios; los documentos, liquidaciones cerradas y payouts permanecen intactos. Los borradores deben revisarse de nuevo si cambia su fuente.

## Concurrencia y seguridad

Transacción SQLite BEGIN IMMEDIATE, validaciones bajo bloqueo, huella de estado contra preview desactualizado y clave UUID de idempotencia. El mismo envío devuelve la operación original; reutilizar la clave con otros datos se rechaza. Un fallo revierte movimiento y auditoría conjuntamente. Rutas exclusivas del router administrativo; ninguna ruta nueva pública.

## Migración preparada

`e45b6d10278c → f56c7e21389d`, sin dependencia fiscal. Añade lifecycle/voided_at a ExpensePayment, voided_at a Expense y las tablas ExpensePaymentVoidOperation/ExpenseCorrectionOperation. Conserva filas y columnas anteriores; pagos existentes quedan posted.

Es aditiva en datos y estructura, pero necesita adaptar el trigger previo `expense_payments_immutable_update`: mantiene inmutables todos los datos originales y permite únicamente posted→void con fecha. No basta añadir columnas dejando el trigger previo, porque bloquearía la anulación. Se añaden protecciones de auditoría, movimientos anulados y nuevas devoluciones. El downgrade solo se permite sin auditorías ni pagos anulados y restaura el trigger anterior.

Se prueba upgrade/downgrade/upgrade exclusivamente en copia consistente, comparando todas las columnas originales y comprobando quick_check/foreign_key_check. No ejecutar stamp, upgrade heads ni rama fiscal. Producción sigue en e45b6d10278c. Un futuro despliegue requiere autorización, copia consistente, revisión de triggers y parada controlada de administración; no restaurar una copia sobre operaciones posteriores sin evaluación.

## Validación

Pruebas sintéticas de pagos parciales/completos, correcciones mayores/menores, límites de pago, devoluciones, copropiedad, cierre, borradores obsoletos, concurrencia, doble envío, rollback, auditoría y triggers. Pruebas HTTP reales incluyendo ausencia de importe en anulación, ausencia de campos obligatorios y rutas públicas bloqueadas. Regresión del circuito de gastos, liquidaciones y payouts. Navegador 375/768/1280: formularios, preview, bloqueos e historial; confirmaciones finales reservadas a revisión manual.

Ejemplos aislados en :8129: gasto 2 pago erróneo pendiente de anulación; gasto 3 total300/pagado100, corregible a200 dejando100 pendiente; gasto1 bloqueado por cierre de un copropietario; gasto4 muestra ambas anulaciones ya auditadas. No contienen datos reales.

No hay cobro bancario ni regularización automática de pagos reales. Las operaciones con devoluciones o consumos cerrados requieren un futuro circuito específico, sin reescribir el histórico.

### Resultado de la ejecución del candidato

- 75 passed: `tests/unit/test_expense_corrections.py tests/unit/test_expense_service.py tests/unit/test_owner_settlement_service.py tests/integration/api/test_expense_corrections_http.py tests/audits/test_expense_corrections_migration.py`.
- 23 passed: `tests/unit/test_expense_categories.py tests/unit/test_provider_expense_ui.py`.
- Repetición final de `tests/audits/test_expense_corrections_migration.py`: 1 passed, incluyendo trigger legacy.
- Navegador real Edge/Playwright: 375/768/1280, sin errores JavaScript ni desbordamiento de página; preview correcto sin ejecutar confirmaciones finales de los ejemplos.
- Copia migrada y candidato sintético: quick_check ok y foreign_key_check vacío. Producción comprobada solo en lectura: e45b6d10278c, integridad correcta.
- Git diff --check sin errores; revisión de whitespace del diff del candidato sin incidencias. Los 15 archivos del candidato están separados del árbol de ejecución y del trabajo pendiente de reutilización de inquilinos.
