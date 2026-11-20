# Pérdidas reconocidas y responsabilidades — subfase 4.1

Implementado en candidato aislado, no desplegado. No implementa comisiones (4.2), aplicaciones de acuerdos (4.3), ni contrapartidas posteriores (4.4).

## Modelo y límites
OwnerTransferRegularizationOperation es inmutable. Registra reconocimiento o asignación de una responsabilidad pendiente, incidencia, importe, responsable, propietario autorizado cuando proceda, acuerdo, evidencia y su referencia, motivo, operador disponible, UTC, estados anteriores y posteriores, idempotencia y huella de revisión.
Una referencia documental normalizada identifica una pérdida dentro de la incidencia; no puede reutilizarse con otro request_key. Partes distintas requieren apartados/documentos distintos y nunca pueden superar el residual no reconocido. El sistema no puede certificar que un documento externo sea veraz.

La asignación posterior conserva el importe íntegro del reconocimiento y solo admite pendiente → gestor/propietario una vez. Para repartir responsabilidades, registrar tramos separados desde el inicio. No hay reasignaciones destructivas ni reversión de reconocimientos en 4.1.
Responsabilidad de propietario: acuerdo expreso, evidencia, confirmación y pertenencia a la atribución acreditada de los fondos. No puede superar su parte no recuperada, descontando responsabilidades ya asignadas. El destinatario accidental nunca se convierte automáticamente en responsable. Sin atribución de fondos no se admite cargar responsabilidad a un propietario.

## Proyección sin efecto económico
Se mantienen exactamente los pagos válidos, obligación pendiente, fondos disponibles, déficit y bloqueos. No se crean Expense, ExpensePayment, OwnerPayout, devoluciones, recuperaciones ni consumos de liquidación. Los PDF y cierres existentes no cambian; reconocer pérdida no genera una nueva versión PDF económica.

Residual no recuperado = importe afectado de la incidencia − recuperaciones efectivas. Las devoluciones anteriores ya están descontadas del importe afectado, no se restan otra vez.
Pérdida reconocida = suma histórica de reconocimientos (las asignaciones no suman otro importe).
Saldo sin reconocimiento = máximo(0, residual − pérdida reconocida). Es una clasificación informativa, no una renuncia ni una baja del derecho de reclamación. El total todavía no recuperado continúa visible y no se reduce por reconocer pérdida.

Si entra dinero después de un reconocimiento, se registra por la fase 3 y se restituye solo lo realmente recibido. La pérdida histórica no se modifica. Se muestra una advertencia de regularización pendiente 4.4 y el posible solapamiento; se bloquean nuevos reconocimientos para evitar conclusiones automáticas sobre a qué tramo corresponde la recuperación. No se aplica ni revierte un acuerdo ni compensación. Las huellas de pagos y recuperaciones incorporan las operaciones nuevas para detectar concurrencia.

Cuenta incorrecta con recepción acreditada: no se presume pérdida, se bloquea este circuito. Comisiones y otros hechos distintos requieren la siguiente subfase.

## Seguridad y migración
Migración 4ab1c368de23, dependiente exclusivamente de 39a0b257cd12. Una tabla, índices y triggers nuevos de inmutabilidad, límite acumulado y relación con reconocimiento original. No modifica triggers de OwnerPayout. Downgrade solo con tabla vacía. Probar sobre copia; no stamp ni upgrade heads.
Los endpoints están solo en administración. Evidencias son referencias textuales; no hay gestor de adjuntos nuevo ni validación de firma digital. Las cuentas completas se enmascaran en textos persistidos y estados auditados. Motivo y confirmaciones se revalidan en servidor. Se reutiliza BEGIN IMMEDIATE, rollback y claves únicas.

## Pruebas
Pruebas específicas de pérdidas parciales/totales, responsabilidad, acuerdos, duplicados/exceso, devoluciones y recuperaciones anteriores, recuperación posterior, copropiedad, déficit, atribución desconocida, concurrencia, rollback, idempotencia, previews desactualizadas, HTTP y PDF históricos. Regresión de fase 3, liquidaciones y documentos. El informe privado del candidato registra resultados exactos.
