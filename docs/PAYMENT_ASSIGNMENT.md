# Asignación posterior de cobros

## Estado
Implementado, validado manualmente y desplegado con autorización. El despliegue no modificó datos de negocio. Reutiliza Payment, PaymentAllocation, FinancialService. No crea ni duplica pagos. No modifica registro inicial de cobro ni custodia. No afecta reservas, disponibilidad, Personas o fiscalidad.

## Auditoría inicial
ManualPaymentService.register admite saldo sin aplicar mediante aceptación explícita allow_unallocated. PaymentRegistration protege el alta del cobro, pero su relación única con Payment impide usarlo como historial de múltiples asignaciones posteriores.
El saldo individual es Payment.amount menos la suma de sus PaymentAllocation. FinancialService.charge_balance calcula el pendiente del cargo incluyendo devoluciones contabilizadas. La restricción única (payment_id, charge_id) evita duplicar parejas. FinancialService.allocate realiza una asignación individual y no ofrece el protocolo de revisión, operación múltiple atómica ni replay requerido por esta UI; el nuevo servicio reutiliza sus cálculos, sin llamar a un método que confirma cada cargo por separado.

## Flujo
Cuenta económica → Cobros pendientes de asignación → Asignar cobro → introducir importes por cargo → Revisar asignación → aceptación explícita → Confirmar asignación.
El listado es por reserva. No hay importes preseleccionados. Se permite dejar saldo pendiente y asignar a varios cargos. La confirmación redirige al historial con saldos actualizados. Pagos y devoluciones conserva el enlace «Ver asignaciones e historial», también para cobros agotados.
Los errores esperables se muestran en HTML mediante avisos. Los errores inesperados no se ocultan.

## Protecciones
Solo cobros posted/receipt y cargos posted/debit de la misma reserva y moneda. Importes positivos; ni exceso sobre pago ni sobre cargo; sin cargos repetidos. Los cobros con devoluciones/correcciones o vinculados a adeudos SEPA requieren revisión independiente. Los cargos reservados en una remesa activa se bloquean para evitar doble cobro.
Criterio conservador: si el pago o el cargo tiene alguna allocation consumida en liquidación cerrada, esta pantalla no permite nuevas asignaciones sobre él, aunque pueda quedar un remanente. No se modifica ni se reasigna nada ya liquidado. No se reabre una liquidación histórica.
La confirmación usa BEGIN IMMEDIATE, vuelve a leer saldos y consumos, y compara una huella con la vista previa. La clave UUID única de operación permite repetir el mismo envío sin duplicar asignaciones; reutilizarla con otros datos se rechaza. Otra operación concurrente invalida la vista previa. Si falla la escritura de auditoría se revierte toda la distribución.

## Trazabilidad y esquema
Nueva PaymentAllocationOperation: clave de petición, Payment, huella de solicitud y revisión, importe total, fecha UTC y detalle por allocation/cargo con importe previo, incremento e importe final. No se guardan datos personales ni bancarios. Si la pareja ya existía, se incrementa solo cuando no tiene consumos protegidos; se mantiene su identificador y la operación documenta el incremento. Las operaciones previas no se reescriben. Triggers SQLite bloquean UPDATE/DELETE del diario; downgrade rechaza eliminar un diario no vacío.
Migración aditiva d34a5c0f167b, dependiente exclusivamente de c2394bfe056a. Crea una tabla, índice y triggers; sin backfill, ni alteración de Payment/PaymentAllocation. Probada en copia consistente con upgrade/downgrade/upgrade y comparación de registros anteriores. No se ejecuta a01729dbe348, ni stamp, ni upgrade heads. Para futuras instalaciones se requiere autorización y migración dirigida antes de cargar los componentes que consultan el diario.

## Liquidaciones posteriores
OwnerSettlementService selecciona allocations no consumidas de cobros anteriores al fin del periodo, por lo que una asignación posterior aún no consumida puede aparecer en una próxima liquidación elegible. Conserva la fecha original del cobro; no modifica retrospectivamente liquidaciones cerradas. Se mantiene la validación de huella existente al cerrar borradores de liquidación.

## Ejemplo sintético
Cobro 600 EUR. Dos mensualidades de 400 EUR pendientes. Asignación de 200 EUR y 100 EUR: queda saldo sin aplicar de 300 EUR, pendientes de cargos 200 EUR y 300 EUR. Existe un único Payment y una operación auditada con dos líneas. La demo permite continuar asignando el remanente.

## Validación
Pruebas de saldo totalmente libre y parcial, varias mensualidades, misma pareja, cruces, moneda, exceso de pago/cargo, replay, concurrencia, revisión obsoleta, aceptación explícita, rollback, liquidaciones cerradas, remesas activas, devoluciones, privacidad pública, actualización de saldos e historial.
Navegador real 375/768/1280: selección, revisión, confirmación sintética, saldos e historial; sin overflow horizontal ni errores JavaScript. No hay JavaScript nuevo: formularios nativos y validación completa del servidor.
La interfaz incluye fechas, métodos, cargos y saldos; no expone información bancaria adicional. Rutas únicamente administrativas.

Validación previa al despliegue: 121 passed en la batería consolidada (asignación, migración, pagos/devoluciones, SEPA, cuenta económica, liquidaciones e inicio contable). Se repitió con éxito un test de historial tras el último ajuste de navegación; es una prueba solapada, no se suma al total. Único aviso: deprecación preexistente Starlette/httpx. quick_check ok y foreign_key_check limpio en copia migrada, demo y producción consultada en modo lectura. En aquella validación, producción permaneció en c2394bfe056a, sin la tabla nueva y con pagos/cargos/allocations a cero.

## Despliegue validado
Aplicada exclusivamente d34a5c0f167b desde c2394bfe056a, sin rama fiscal. Instalados ocho componentes cuyos hashes coinciden con el candidato. Administración responde HTTP 200 y muestra el listado vacío; las pantallas y preview se comprobaron además con los componentes instalados sobre la demo abierta en solo lectura. Tabla de auditoría vacía, huellas de negocio conservadas, quick_check ok y foreign_key_check limpio. Solo se reinició administración. Un primer intento revirtió el código por puerto ocupado; el reintento con espera acotada finalizó correctamente sin repetir la migración. Backup y procedimiento de reversión se conservan fuera de Git.

Cierre en Git: 40 pruebas finales específicas superadas sobre HEAD más exclusivamente los once archivos del bloque (asignación posterior, pagos/devoluciones y Cuenta económica). Los ocho componentes de ejecución coinciden con los hashes desplegados. Sin migraciones ni reinicios durante el cierre; se conserva la validación de migración previa. git diff --cached --check correcto.
