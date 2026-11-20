# Recuperaciones efectivas de transferencias — fase 3

## Estado y alcance
Implementado exclusivamente en candidato aislado. No desplegado. Producción permanece en 289fa146bc01. No se realizan operaciones bancarias, consultas bancarias, recuperaciones automáticas ni regularizaciones excepcionales de fase 4. VERI*FACTU fuera del alcance.

## Movimientos y auditoría
OwnerTransferRecovery registra un abono ya recibido, vinculado a la incidencia que identifica de forma inmutable la cadena de payout original o la salida extraordinaria. Conserva importe, fecha, huella/terminación de cuenta receptora, referencia, identificador, motivo/evidencia, operador disponible, fecha UTC, declaración de recepción, idempotencia, huella revisada, distribución e impacto.

OwnerRecoveryAttribution completa una distribución pendiente una sola vez, sin editar el ingreso. OwnerRecoveryReturnLink vincula documentalmente una devolución anterior sin crear otro ingreso. OwnerBankCreditIdentity centraliza nuevas identidades de abonos; los controles consultan además los registros históricos que carecen de identidad auxiliar, sin backfill financiero. OwnerPayoutReview conserva motivo, identidad, vista previa e impacto del pago ordinario.

Todas las tablas nuevas son inmutables. Los registros originales, cuentas históricas, liquidaciones cerradas y versiones PDF anteriores no se modifican. Los nuevos PDF pueden mostrar las recuperaciones atribuibles al propietario del documento.

## Fórmulas y casos
Para una transferencia errónea no recibida válidamente, recuperar dinero disminuye la salida neta y el pendiente de recuperar; no satisface la obligación con el propietario. Su importe afectado continúa excluido del pago válido original. Un nuevo payout correcto sí satisface esa obligación una vez.

Para cuenta incorrecta del mismo propietario con recepción acreditada, el pago original sí era válido: su recuperación reduce el pago válido y aumenta la obligación pendiente. El máximo recuperable no significa que se exija una deuda al propietario.

Las recuperaciones de salidas extraordinarias duplicadas restituyen fondos; no restan el pago legítimo original. Los déficits se reducen antes de liberar disponibilidad. Disponible nunca negativo; déficit visible por separado.

Ejemplo: fondos 200, payout erróneo 100, recuperación 40: pago válido 0, obligación pendiente 200, fondos disponibles 140. Nuevo pago correcto 40: pago válido 40, pendiente 160 y disponible 100. El payout erróneo permanece intacto.

## Devoluciones anteriores y duplicados
Ejemplo: payout 100, devolución anterior 40, incidencia residual 60, recuperación nueva 30. La devolución anterior sigue contabilizada una sola vez; el pendiente de recuperar es 30, no se descuentan otra vez los 40 anteriores. El vínculo documental no tiene impacto económico.

Identificador bancario normalizado + huella de cuenta receptora permite rechazar el mismo abono entre devoluciones y recuperaciones. Sin identificador fiable se comparan fecha/importe y cuenta o salida relacionada; cambiar referencia libre o cuenta no elude una coincidencia de la misma salida. Abonos parecidos solo se distinguen con identificadores bancarios distintos y evidencia. Bajo bloqueo transaccional se repiten comprobaciones, límites y huellas. Las guardas SQL refuerzan inmutabilidad, límites, distribución y duplicados cruzados.

## Fondos compartidos o desconocidos
Propietario único identificado: asignación automática exclusivamente a sus fondos. Varios propietarios: distribución explícita, suma exacta y límites por titular según la salida original menos lo ya restituido. No se acredita al destinatario accidental.

Sin atribución de origen, el abono se registra recibido pero no disponible. Primero se atribuye la salida mediante el circuito existente; después cada recuperación pendiente requiere una atribución auditada. El cálculo resta la salida y suma cada abono una sola vez. Se conserva el bloqueo general o del ámbito identificado mientras queden atribuciones desconocidas/incompatibles, incluso si el dinero se recuperó íntegramente.

## Nuevo pago correcto
La UI usa OwnerPayoutReviewService para preparar el impacto y confirmar mediante OwnerSettlementService.payout. No hay un segundo mecanismo de pagos. Se revalida dentro de la transacción ordinaria: pendiente, fondos, bloqueos, devoluciones incompatibles, cuenta activa del propietario y posibles duplicados.

Máximo = menor entre pendiente y fondos disponibles, si no hay bloqueos. La cuenta histórica puede estar inactiva para registrar una recuperación; un nuevo pago exige una cuenta activa. No se modifica la cuenta anterior.

La vista previa y confirmación requieren motivo y declaración de que el nuevo pago ya se ejecutó. Ante movimientos similares de fecha/importe/destino se exigen identidades distintas y cuenta de origen verificable. Los IDs auxiliares enlazan la cadena anterior sin modificar OwnerPayout. La vía administrativa de correcciones conserva sus bloqueos.

## Migración
39a0b257cd12 depende exclusivamente de 289fa146bc01. Cinco tablas nuevas, índices y triggers aditivos. No modifica los triggers originales de OwnerPayout ni ejecuta la rama fiscal. Probada mediante upgrade/downgrade/upgrade únicamente en copia consistente. No usar stamp ni upgrade heads.

Una reversión de esquema se bloquea si las tablas nuevas tienen registros. No restaurar código que ignore recuperaciones ya registradas: daría saldos incorrectos. Un futuro despliegue requiere autorización, backup consistente y comprobación de esquema/manifiesto.

## Validación y límites
Pruebas sintéticas unitarias y HTTP cubren recuperaciones, exceso, identidad cruzada, atribución posterior, copropiedad, déficit, cuenta histórica, concurrencia, stale preview, idempotencia, rollback, nuevo payout, cierre y PDF. Pruebas de migración verifican guardas e integridad. El informe privado del candidato conserva comandos y resultados exactos.

No hay integración bancaria ni validación automática de justificantes. Se requiere evidencia veraz del operador. Una recuperación se aplica a una incidencia; los abonos bancarios agrupados que correspondan a varias salidas requieren diseño específico y no deben fraccionarse fingiendo identidades distintas. No se editan, anulan ni redistribuyen recuperaciones confirmadas; correcciones excepcionales pertenecen a fase 4. No se condonan importes ni se añaden comisiones/diferencias de cambio. No se identifica automáticamente al beneficiario desconocido. Los enlaces documentales solo admiten devoluciones de la misma cadena.
