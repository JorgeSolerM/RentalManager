# Finalización anticipada de reservas activas

## Aislamiento y despliegue

Implementación preparada inicialmente en una copia privada del árbol, incluido el trabajo pendiente de facturación, sin modificar los archivos originales durante su validación. Antes de publicar se desacoplaron sus dependencias: el checkpoint versionado funciona sin código ni tablas de Facturación/VERI*FACTU.

Cadena publicada: `fe0618cad237 → b1283aedf459`. La consulta de facturas es de solo lectura y opcional por presencia de tabla; no importa modelos del módulo pendiente. Si la tabla existe pero es incompatible, el error no se oculta.

Tras autorización expresa del usuario, el 13/10/2026 se integró el parche, se creó y verificó un backup privado, se aplicó `b1283aedf459` a la BD real y se reinició exclusivamente la tarea administrativa. La comprobación posterior confirmó integridad, conservación de los datos de negocio y cero finalizaciones reales. No se reiniciaron web pública, Cloudflared ni tarea iCal. No se hizo commit/push.

## Fechas

- `Booking.check_out`: salida efectiva exclusiva; la habitación queda libre ese día.
- `BookingEarlyTermination.original_check_out`: fecha anterior conservada, no editable.
- `economic_last_day`: último día a cargo **incluido**, confirmado por el usuario. El plan convierte a límite exclusivo sumando un día. 31 de marzo incluye todo el 31.
- Por defecto se propone la fecha de salida como último día a cargo; una elección económica manual nunca se sobrescribe.
- La salida debe acortar una reserva ya iniciada; puede ser pasada, de hoy o programada. El estado visible depende de la fecha, no se cancela anticipadamente una salida futura.
- Una renta por mes natural. Se reutiliza el prorrateo existente por días reales y se exige revisión explícita para un último mes parcial. No se habilitan múltiples versiones.

## Revisión y confirmación

La revisión solo lee. Muestra ocupación liberada, otras reservas, cargos y cobros, adeudos/remesas, vínculos de mandato, liquidaciones/facturas relacionadas y plan futuro. No guarda ni genera cargos.

La confirmación usa la transacción financiera serializada, fingerprint de los datos revisados, clave UUID idempotente y restricciones de unicidad. Si cambia el formulario debe revisarse otra vez. Si cambian los datos se rechaza una confirmación obsoleta. La fecha anterior, motivo, notas, momento y snapshot quedan en un registro inmutable; no se inventa un usuario autenticado cuando la aplicación no lo proporciona.

## Política económica conservadora

Se bloquea cuando hay cargos no anulados que exceden o atraviesan el límite económico, incluso borradores. Los conceptos de fianza independientes se conservan. Hay que resolver los cargos por sus operaciones explícitas antes de repetir la revisión; esta función no anula, elimina, devuelve, compensa ni rectifica nada.

Los adeudos afectados añaden un bloqueo bancario explícito. Cambiar la Booking nunca cancela una orden externa. Mandatos, XML, identificadores y hashes exportados permanecen intactos. Pagos, allocations, liquidaciones y facturas se conservan.

Las nuevas rentas ordinarias y generaciones de plan respetan el límite económico, independiente de la salida física. No se usa Room.base_price ni se generan Payments.

## iCal y calendario maestro

Una reimportación no reemplaza fechas administrativas protegidas. Se conservan identificadores y se registra la última fecha comunicada por el feed; si difiere, el ciclo reporta warning y la ficha expone el conflicto. No se realiza ninguna llamada de modificación a plataformas externas. El runner no cambia.

La auditoría detectó una convención legacy específica del calendario maestro (DEC-018/019: DTEND calculado con +1 día). Se mantiene para reservas legacy. Para una finalización explícita nueva se exporta DTEND igual a la salida efectiva exclusiva, evitando retener un día adicional. No se modifica globalmente el parser ni se reinterpretan reservas históricas.

## Migración y validación

Dos tablas auxiliares y tres triggers, sin backfill económico ni cambios a filas existentes. Upgrade/downgrade/reupgrade se prueba en copia privada de la BD. Downgrade con historial de finalización se bloquea para no destruir auditoría.

### Compatibilidad con el despliegue privado anterior

Las revisiones aún no publicadas se separaron antes del primer commit. La BD real ya estaba marcada `b1283aedf459` y contenía también las tablas privadas de facturación: conserva ese marcador y todas sus tablas/datos. No se ejecuta `stamp`, downgrade ni migración real para el desacoplamiento. En un checkout limpio, `upgrade b1283aedf459` reconoce ese estado sin escrituras; en una instalación nueva solo crea el esquema publicado de finalización.

La migración de facturación `a01729dbe348` permanece **fuera de este checkpoint**, ahora como sucesora pendiente de `b1283aedf459`. Su futuro upgrade debe crear el esquema si no existe o verificar íntegramente tablas/índices/triggers antes de adoptar el ya existente, sin tocar filas. Un esquema parcial o distinto debe bloquearse. Por eso el head de un workspace con facturación pendiente puede diferir del único head del commit publicado. No adelantar esa revisión en producción hasta cerrar y autorizar el bloque de facturación.

Las copias antiguas marcadas únicamente `a01729dbe348` pertenecen al grafo privado anterior; deben restaurarse con su snapshot de código correspondiente y revisarse antes de actualizar, nunca corregirse mediante un `stamp` automático. Se conserva una copia privada del código previo al desacoplamiento.

Casos sintéticos A–G: sin economía; borrador futuro; cargo posted; pago parcial; SEPA presentada; importada con discrepancia; salida futura. Se preparan exclusivamente en entorno aislado. La validación de navegador revisa los previews y no acepta diálogos finales en nombre del usuario.

Limitación intencionada: no existe edición destructiva de una finalización ya confirmada ni resolución automática de sus discrepancias económicas. Un cambio posterior requerirá un flujo auditado específico.
