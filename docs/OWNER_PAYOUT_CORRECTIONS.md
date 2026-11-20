# Corrección administrativa de pagos a propietarios

Estado: candidato aislado en :8130. Pendiente de validación manual y autorización de despliegue. No hay cambios de producción.

## Alcance

Fases 1 y 2: saldo común y rectificaciones administrativas. No se ordenan transferencias ni devoluciones. Las transferencias reales a beneficiarios equivocados y sus recuperaciones quedan fuera del circuito. La confirmación del operador distingue un error de registro de un movimiento real; la aplicación no puede verificar por sí sola el extracto bancario.

OwnerPayout permanece inmutable. Una operación append-only puede anular su efecto o enlazar un sustituto del mismo propietario, liquidación, cuenta histórica y método. Fecha, importe y referencia se corrigen mediante ese sustituto. El original conserva todos sus campos. La tabla nueva guarda motivo, UTC, operador cuando la autenticación suministre request.state.operator_id, estados antes/después, impacto, declaración, huella y UUID de idempotencia. No se acepta identidad de operador desde el formulario. No se duplican titular ni IBAN completo en snapshots de auditoría; se guarda la terminación de cuenta y las referencias se sanitizan.

La ausencia de una identidad autenticada se muestra expresamente, sin atribuir la operación a un usuario ficticio.

## Saldo y documentos

OwnerPayoutBalanceService es la fuente común de pagado efectivo, pendiente, fondos disponibles por propietario y estado de pago. Excluye originales invalidados y cuenta una sola vez el último sustituto vigente. Los estados posted/void/replaced se derivan del historial, no se escriben en el payout original. El estado económico closed y el snapshot de la liquidación no cambian.

Se usa en registro de nuevos payouts, pantalla administrativa y generación de documentos. Los PDF ya emitidos no se modifican ni se regeneran automáticamente. Una generación manual posterior crea una versión nueva con el saldo vigente y conserva la anterior.

## Protecciones

BEGIN IMMEDIATE, revalidación bajo bloqueo, huella de todos los payouts/operaciones/cierres del propietario, transacción atómica y UUID de idempotencia. El mismo envío no crea otro sustituto; reutilizar la clave con otros datos se rechaza. Un fallo de auditoría revierte también la inserción del sustituto.

Límite por liquidación y por fondos globales del propietario, descontando primero el original. No se cambia beneficiario ni liquidación. No se exige que la cuenta histórica siga activa. Se bloquean registros ya invalidados, destinos ambiguos, devoluciones de rentas pendientes, liquidaciones con agrupación de facturación y compensaciones vinculadas. El control existente de FeeCompensationService basado en cualquier payout permanece intacto. La comprobación adicional de compensaciones es de solo lectura y comprueba primero la existencia de la tabla: no exige aplicar la rama fiscal.

Los casos bancarios reales incompatibles requieren un procedimiento posterior. No se representan mediante anulaciones administrativas, saldos negativos artificiales ni ajustes silenciosos.

## Migración

f56c7e21389d → 067d8f3249ae. Dependencia económica única. Solo crea owner_payout_correction_operations y triggers de auditoría inmutable/destino coherente. No altera columnas ni triggers existentes de OwnerPayout. FK restrict, original y sustituto únicos, forma de operación válida y enlace de sustitución ascendente para impedir ciclos.

Probada upgrade/downgrade/upgrade en una copia consistente de producción. Se comparan todos los datos originales y los triggers anteriores. El downgrade se bloquea si existe historial. No usar stamp, upgrade heads ni ejecutar migraciones fiscales. Un despliegue futuro exige autorización, copia consistente y revisión del código instalado; nunca restaurar una copia antigua sobre operaciones posteriores.

## Validación sintética

Pruebas de pagos parciales/completos, duplicados, aumentos/reducciones, fechas/referencias, cuenta inactiva, destino incorrecto, PDF/versiones, fondos compartidos, concurrencia, doble envío, rollback, preview desactualizado, cadenas de sustituciones, privacidad y HTTP real sin campos obligatorios. Rutas no expuestas en la app pública.

Navegador Edge/Playwright a 375/768/1280: preview, confirmaciones no preseleccionadas, cuenta enmascarada, bloqueo visible, historial y ausencia de overflow de página/errores de consola. No se ejecutan las confirmaciones finales de los ejemplos de revisión.

## Ejemplos manuales

- /settlements/1/payouts/1/review?kind=void: anulación administrativa, 100 registrados; saldo pendiente vuelve a 200 al confirmar.
- /settlements/2/payouts/2/review: corregir pago parcial de100 a150; pendiente pasa de100 a50.
- /settlements/3/payouts/3/review: corregir fecha o referencia manteniendo importe100.
- /settlements/4/payouts/4/review: bloqueo por devolución de renta pendiente en la base sintética.
- /settlements/5/payouts/5/review: original100 sustituido por150, ambos conservados y solo150 computables.

Los datos de estos ejemplos son sintéticos. La copia real usada para validar migración no se sirve por la aplicación ni se incluye en Git. No se alteran output/, reutilización de inquilinos ni VERI*FACTU.

## Resultados del candidato

- Batería consolidada: 62 passed (test_owner_payout_corrections.py, test_owner_payout_corrections_http.py, test_owner_payout_corrections_migration.py y test_owner_settlement_service.py).
- Tanda final tras incorporar el bloqueo explícito por compensaciones existentes: 28 passed en los tres archivos específicos de correcciones. Incluye repetición de pruebas ya contadas en la consolidada.
- Regresión previa de liquidaciones y migración: 36 passed, incluyendo payouts y PDF.
- Migración en copia consistente: upgrade/downgrade/upgrade correcto; datos y triggers originales conservados.
- quick_check ok y foreign_key_check vacío en candidato, copia migrada y comprobación de producción en solo lectura. Producción continúa en f56c7e21389d.
- Diff del candidato y git diff --check sin errores. Backend productivo comparado por hashes y sin cambios.
- Edge a375/768/1280: formularios, previews, bloqueos e historial correctos, sin errores de consola ni overflow de página. No se ejecutaron confirmaciones finales de los ejemplos.
