# Cobros y remesas BBVA

## Nombre administrativo de remesa

`SepaBatch.name` es opcional, admite hasta 160 caracteres Unicode y se normaliza
con trim; vacío se guarda como NULL. No es único. El fallback visible es
`Remesa {id}`, sin persistir nombres artificiales. Puede indicarse al crear y
modificarse inline con el lápiz **Editar nombre de la remesa**, cualquiera que sea el
estado, incluidas devoluciones y cancelación.

La edición solo modifica `name`. No cambia la referencia técnica, fechas, acreedor,
importes, adeudos, pagos, aplicaciones ni artefactos. No genera ni modifica XML:
el nombre nunca se utiliza como MsgId, PmtInfId o EndToEndId. La referencia interna
se conserva visible en segundo plano. La ficha mantiene Nueva remesa y la navegación
lateral Cobros, sin el botón redundante Remesas.

No hay una franja permanente de edición. El lápiz junto al título aparece con
hover/foco en escritorio y permanece visible en tablet/táctil. Enter o ✓ guarda;
Esc o × cancela y devuelve el foco al lápiz. Se conserva el mismo endpoint de
renombrado y la semántica de nombre vacío.

Revisión `bac2e4f6d893`, sobre `a9c1e3f5b782`: añade únicamente esta columna nullable,
sin backfill. El downgrade elimina los nombres administrativos, no las remesas ni
su histórico bancario; debe conservarse backup si ya se han configurado nombres.

## Alcance y separación contable

`BookingCharge` es la deuda contabilizada; `SepaDebit` es una instrucción bancaria;
`Payment` es un cobro registrado explícitamente. Preparar, exportar y presentar no
crean pagos. No se convierten precios legacy ni se generan cargos automáticamente.

En `/collections` se configura un único iniciador/presentador (nombre e
identificador), independiente del acreedor. Es información administrativa; no se
rellena desde archivos históricos ni desde datos del titular de la web.

El periodo significa **mes de vencimiento**: `due_date` dentro de ese mes. Se
incluyen exclusivamente cargos `posted`, dirección `debit`, con saldo positivo,
de tipo renta, fianza, suministros o extraordinarios. Se reutiliza el cálculo de
saldo del ledger, incluidas las asignaciones parciales. Créditos/descuentos no se
convierten en adeudos positivos ni se netean sin una futura regla explícita.

## Resolución y agrupación

La finca se resuelve desde Booking → Room → Property; sus titularidades activas
y vigentes para la fecha de cobro proporcionan las cuentas de rentas activas.
Se requieren perfil acreedor activo CORE, cuenta EUR y un vínculo explícito
`BookingSepaMandate` activo con un mandato activo y completo. Una selección previa
de mandato puede desambiguar varios acreedores compatibles. Sin esa selección no
se elige arbitrariamente un propietario. `Person.iban` nunca autoriza un adeudo.

Una remesa lógica (`SepaBatch`) contiene grupos (`SepaBatchGroup`) por perfil
acreedor/cuenta. Dentro de cada grupo se agregan los cargos de una misma Booking
y mandato; todos usan la fecha solicitada de la remesa. Se conserva el desglose
en `SepaDebitChargeAllocation` y una instantánea privada de los datos exportables.

Cada grupo produce un XML independiente. RCUR y OOFF, si coexisten, forman
`PmtInf` separados dentro del XML del grupo. Un mandato OOFF no puede generar
varios adeudos ni reutilizarse una vez reservado/presentado. Los cambios de mandato
(`AmdmntInd=true`) quedan bloqueados porque faltan los datos de la modificación.

## Compatibilidad observada y límites

Se han estudiado siete XML privados aceptados por BBVA, exclusivamente desde
`data/sepa_reference/`. No se importan, modifican, versionan ni registran sus valores.
Características comunes observadas:

- namespace `urn:iso:std:iso:20022:tech:xsd:pain.008.001.02`;
- un `GrpHdr` y un `PmtInf` por original;
- `DD`, `SEPA`, `CORE`, `RCUR`, `BtchBookg=true`, `AmdmntInd=false`;
- iniciador global con `InitgPty/Id/PrvtId/Othr/Id`;
- acreedor con `CdtrSchmeId/Id/PrvtId/Othr/Id` y esquema propietario `SEPA`;
- BIC de acreedor y de cada deudor, mandato y fecha de firma;
- cantidades de adeudos: 10, 3, 1, 2, 2, 3 y 7;
- IBAN ES, DE, NL, LT, FR y PT; totales coherentes en ambas capas;
- un iniciador común y tres cuentas acreedoras distintas en el conjunto.

Los originales contienen direcciones postales de acreedor, algunas direcciones de
deudor e identificadores privados del deudor. Estos elementos opcionales se
conservan estructuralmente en los fixtures, pero **no se inventan en el exportador**
cuando no existen datos bancarios fiables para ellos en el modelo. No se toma una
dirección de Person como dirección de un titular bancario que podría ser un tercero.
El Test de ficheros de BBVA ha aceptado el XML generado sin dirección postal ni
identificador privado del deudor. Se mantiene su omisión: no se añaden por ahora.
Este resultado no certifica todas las variantes futuras de cuenta, canal o país.

Como todos los ejemplos proporcionados llevan BIC, se exige BIC válido para este
perfil de exportación: no se deduce del IBAN ni se inserta `NOTPROVIDED` sin una
confirmación de compatibilidad. OOFF y varios grupos son casos nuevos probados
estructuralmente, no archivos cuya aceptación por BBVA se haya demostrado aquí.

No se ha incorporado un XSD oficial al repositorio. La validación actual comprueba
estructura, namespace, campos obligatorios, referencias, importes y sumas, además
de IBAN MOD-97 y BIC. **No se presenta como validación XSD.** Referencia documental
complementaria: [Guía CORE ISO 20022 de CECA](https://www.ceca.es/wp-content/uploads/2021/06/Cuaderno_Guia_SDD_Core_Nov-2019.pdf).
Los XML históricos privados no se enviaron a validadores externos. El usuario
probó posteriormente un fichero nuevo del exportador en el Test de ficheros de BBVA.

### Revisión final de compatibilidad

La comprobación local incluye el repositorio (también directorios ignorados) y
el entorno virtual: no se encontró un XSD. No se descargaron esquemas. La prueba
bancaria posterior se documenta abajo y no equivale a una validación XSD local.

| Elemento | Histórico BBVA | Exportador | Coincidencia |
| --- | --- | --- | --- |
| Namespace | pain.008.001.02 | pain.008.001.02 | Sí |
| GrpHdr | MsgId, CreDtTm, NbOfTxs, CtrlSum | Mismos elementos y totales recalculados | Sí |
| InitgPty | Nm e Id/PrvtId/Othr/Id | Configuración global, instantánea por remesa | Sí |
| PmtInf | PmtInfId, DD, BtchBookg=true, fecha de cobro | Mismos elementos | Sí |
| PmtTpInf | SEPA / CORE / RCUR | SEPA / CORE / RCUR en la muestra | Sí |
| Acreedor | Cdtr, CdtrAcct, CdtrAgt/BIC, CdtrSchmeId | Mismas rutas bancarias | Sí |
| Adeudo | EndToEndId, InstdAmt EUR | Mismos elementos | Sí |
| Mandato | MndtId, DtOfSgntr, AmdmntInd=false | Mismos elementos | Sí |
| Deudor | Nm, cuenta IBAN, BIC | Mismos elementos | Sí |
| Concepto | RmtInf/Ustrd | Concepto generado desde cargos y estancia | Sí |
| Direcciones postales | Acreedor y algunos deudores | No exportadas | No |
| Identificador privado del deudor | Presente | No exportado | No |

La primera muestra descargable se generó desde una administración aislada con datos
sintéticos, no copiando un XML histórico. Sus IBAN tienen checksum válido y sus
identificadores acreedores de prueba llevan dígitos de control calculados. Los
BIC TEST son sintácticamente válidos, pero no identifican entidades operativas;
los acreedores e iniciador tampoco están registrados/autorizados en BBVA.
Por tanto sirve para revisar el exportador y su estructura, no para afirmar que
pasará la validación comercial bancaria ni para cursar cobros reales. Si el
validador exige datos registrados, hay que acordar una prueba bancaria específica
sin enviar órdenes de cobro. La prueba posterior autorizada se describe a continuación.

### Resultado del Test de ficheros de BBVA

Según la confirmación del usuario, un XML generado íntegramente por el exportador
de RentalManager superó el Test de ficheros real de BBVA con este resultado:

> Formato de fichero correcto. Envíe su fichero en firme a través de la opción de menú correspondiente.

BBVA lo reconoció como **Adeudos CORE**, con **1 fichero correcto / 0 incorrectos**,
**1 orden** e importe **400,00 EUR**, y reconoció acreedor y cuenta emisora.
Queda validado contra ese test el formato/perfil utilizado:
`urn:iso:std:iso:20022:tech:xsd:pain.008.001.02`, `SEPA`, `CORE`, `RCUR`.

La generación se realizó exclusivamente en un entorno temporal. Como entrada
privada autorizada se utilizaron el iniciador y la configuración acreedora real,
con cuenta BBVA y BIC verificado contra esa misma cuenta en un histórico. El
deudor, su IBAN, el mandato, la Booking, los cargos y conceptos siguieron siendo
de prueba. Ningún dato bancario o identificativo real se incorpora a esta
documentación ni a los fixtures. No se creó actividad económica ni remesas en
la BD real; el Test de ficheros no es presentación en firme ni cobro recibido.

La aceptación valida el formato/perfil probado, pero **no sustituye las
comprobaciones comerciales de cada futura remesa**, la autorización del mandato,
los saldos, las fechas o los datos bancarios. Tampoco acredita OOFF o todas las
variantes de múltiples adeudos. Se mantiene **BIC obligatorio** en esta primera
implementación, sin añadir dirección postal ni identificador privado del deudor.

El checkpoint permanece abierto hasta la confirmación manual del último paso:
remesa presentada → seleccionar adeudos → marcar como cobrados → aceptar diálogo
→ comprobar el resultado visual. Después corresponde ejecutar la revisión final
consolidada de tests, Git, Alembic, integridad, iCal y ausencia de actividad
económica/remesas en la BD real. No se considera cumplida esa revisión por el
resultado bancario ni por las pruebas automatizadas anteriores.

El BIC sigue siendo obligatorio. Su deducción automática queda pendiente.
El iniciador es editable en Cobros; un cambio posterior no altera las instantáneas
de remesas ya creadas. Dos pruebas dirigidas cubren esta persistencia y todos los
elementos exportados enumerados arriba.

## Fixtures y privacidad

`tests/fixtures/sepa_bbva/reference_*.xml` conserva los árboles XML de las siete
muestras, pero reemplaza todas las hojas de negocio: nombres, identificadores,
mandatos, referencias, cuentas, BIC, direcciones, fechas, conceptos e importes.
Solo se conservan constantes del protocolo, países y estructura. Las cuentas son
sintéticas con checksum; los BIC empiezan por TEST y no identifican bancos reales.
Los totales se recalculan. Alquiler + suministros y alquiler + fianza se ejercitan
con conceptos sintéticos; no se afirma que la fianza estuviera presente en los
originales. Los casos de varios acreedores se prueban como grupos separados.

El generador local `scripts/anonymize_sepa_references.py` exige que la carpeta esté
ignorada y rechaza coincidencias de valores privados antes de emitir cualquier
salida. Los tests normales solo leen fixtures sintéticos y no necesitan originales.

## Estados y consistencia

Preparada → Exportada → Presentada → Parcialmente cobrada / Cobrada.
La presentación exige confirmación expresa de haber presentado **todos** los XML
del grupo lógico. No hay envío al banco. El usuario confirma cada adeudo recibido
y su fecha efectiva (no futura). Se crea un Payment `posted`, método
`sepa_direct_debit`, por adeudo, y sus asignaciones siguiendo el desglose reservado.

La operación completa se confirma o revierte en una sola transacción. Los
escritores de Cobros se serializan en SQLite antes de consultar saldos. La clave
idempotente de creación, la reserva única activa de cada cargo, los EndToEndId
únicos (UUID sin datos personales) y el vínculo único con Payment evitan dobles
remesas/cobros por repetición o concurrencia dentro de este flujo. Se revalida el
saldo al exportar y al cobrar; si ha cambiado de forma incompatible, se bloquea la
operación completa. No se encadenan servicios con commits parciales.

Las devoluciones bancarias y cancelaciones locales previas a presentación tienen
las operaciones explícitas descritas abajo. Los reintentos no son automáticos:
crear una nueva remesa tras una devolución conserva el intento original y genera
otro EndToEndId, enlazado mediante `retry_of_id`. Las asignaciones históricas
permiten seguir los cargos entre intentos. No se libera una reserva silenciosamente.

## Pagos manuales y devoluciones bancarias

`Payment` sigue siendo una única entidad del ledger, independiente de SEPA. Los
métodos existentes son `cash`, `bank_transfer`, `sepa_direct_debit`,
`card_or_platform` y `other`. La UI ordinaria permite Efectivo, Transferencia y
Otro; SEPA se registra desde la remesa. No se crea un adeudo ficticio.

En Cuenta económica → Registrar pago se introducen importe, fecha efectiva,
método y referencia/nota opcional. **Proponer distribución no escribe**: reparte
por vencimiento e ID ascendente sobre cargos debit/posted con saldo. El usuario
revisa y puede editar todas las aplicaciones antes de confirmar. No se permite
superar el saldo de un cargo ni el importe del pago. Conservar un resto sin aplicar
exige una casilla explícita; se reutiliza el saldo no aplicado que ya existía en
el ledger, sin gestión nueva de sobrepagos SEPA.

La confirmación crea un Payment posted y todas sus PaymentAllocation en una sola
transacción. `payment_registrations` conserva una clave de solicitud y una huella
de los datos revisados: repetir la misma solicitud no duplica el pago y cambiar
sus datos con la misma clave se rechaza. Esta tabla no depende de SEPA.

Los nuevos flujos de pagos manuales y SEPA comparten una transacción SQLite
`BEGIN IMMEDIATE`: el bloqueo de escritura se adquiere **antes** de consultar
saldos. Se descarta únicamente la transacción previa de lectura, y se rechaza
entrar con cambios pendientes. No se encadenan métodos del ledger con commits
independientes para las operaciones compuestas.

### Pago por otro medio frente a un adeudo

El pago manual no borra ni cancela automáticamente un adeudo. La cuenta económica
y la remesa muestran que el saldo se redujo o se pagó por otro medio.

- **Preparada sin XML:** se pueden excluir adeudos expresamente. Quedan
  `cancelled`, con fecha/motivo, liberando sus reservas de cargos. El exportador
  recibe solo los adeudos vigentes; se conserva todo el historial interno.
- **Exportada pero no presentada:** la acción cancela expresamente la **remesa
  completa**, no modifica los bytes del XML ni crea una falsa versión del mismo
  archivo. Los XML quedan etiquetados como históricos cancelados, NO presentables.
  Se liberan las reservas y hay que crear otra remesa con los saldos pendientes.
  Esto evita mantener un XML aparentemente vigente que todavía incluya el adeudo
  excluido. Si un archivo ya se cargó en el banco, la cancelación local no lo
  retira: la UI exige confirmar que no se ha presentado.
- **Presentada:** se conserva ese estado y se advierte que el banco aún puede
  cobrar el adeudo. No existe cancelación bancaria automática. Se bloquea registrar
  un cobro SEPA cuando no puede aplicarse íntegramente: no se crea otro Payment ni
  se sobredistribuye el cargo. También se revalida el saldo antes de presentar.

Un pago parcial no modifica el importe de una instrucción/XML existente. Revisar
o generar otra remesa es siempre una operación explícita, nunca una edición del
XML histórico. Una cancelación de remesa completa conserva también los adeudos
que no estaban pagados; el motivo distingue estos de «Pagado por otro medio».

### Devolución bancaria posterior a un cobro

Registrar devolución/devoluciones solicita fecha no futura y no anterior al cobro,
motivo opcional y referencia bancaria opcional. Solo acepta adeudos cobrados. En
una transacción:

1. Conserva Payment original posted y todas sus asignaciones.
2. Crea otro Payment posted de dirección `refund`, método `sepa_direct_debit`,
   importe positivo almacenado y `corrects_payment_id` apuntando al cobro original.
3. Crea asignaciones de igual importe a los cargos originales. El ledger ya resta
   las asignaciones refund, por lo que reaparece el saldo pendiente sin editar el
   cargo ni las asignaciones históricas.
4. El adeudo pasa a `returned`, conserva `payment_id`/fecha de cobro y guarda
   `return_payment_id`, fecha efectiva, momento de registro y motivo de devolución.
   Libera la reserva de cargos, no elimina el intento.

El vínculo único con el Payment compensatorio y la serialización evitan doble
devolución. Repetir el mismo adeudo/fecha no crea otro movimiento; una fecha
distinta se rechaza. Si falla cualquier adeudo de una selección múltiple, se
revierte toda la selección. No se permite anular mediante `void_payment` el cobro
SEPA ni su devolución: una corrección administrativa requiere otra operación
auditada futura. **Devolución bancaria no es «marqué cobrado por error».**

La UI conserva «Cobrado DD/MM/AAAA» y añade «Devuelto DD/MM/AAAA». El historial
económico muestra cobros con signo positivo y devoluciones con signo negativo;
eso no cambia los importes positivos almacenados ni la dirección del movimiento.

### Estado agregado

La representación se deriva de los adeudos, sin borrar hitos de la remesa:

| Adeudos vigentes | Presentación de la remesa |
| --- | --- |
| Todos cobrados, ninguno devuelto | Cobrada |
| Algunos cobrados y otros presentados | Parcialmente cobrada |
| Cobrados + devueltos, sin pendientes | Cobrada con devoluciones |
| Devueltos y pendientes, con o sin cobrados | Parcialmente cobrada con devoluciones |
| Todos devueltos | Devuelta |
| Todos cancelados antes de presentar | Cancelada |

El estado persistido `collected` conserva el hito de haber cobrado todos; la
etiqueta derivada distingue sus devoluciones posteriores. Un returned nunca
vuelve a pending. Siguen fuera de alcance conciliación, gastos bancarios,
R-transactions completas, reintentos automáticos y corrección de errores humanos.

### Revisión adicional de esquema

`a9c1e3f5b782` sobre `f8b0d2e4a671` añade `payment_registrations`, los datos de
devolución/cancelación de SepaDebit y amplía sus constraints. No añade columnas
a Payment, Booking o Person, ni introduce backfill. El downgrade se bloquea si
hay devoluciones, cancelaciones o registros de pago manual: no destruye su
trazabilidad para volver a un modelo que no puede representarla.

Antes de migrar la BD real se verifica backup SQLite, ciclo aislado
upgrade/downgrade/reupgrade con guard activo e integridad. Las pruebas incluyen
instrucciones históricas no vacías y bloqueo del downgrade con devoluciones.
El exportador BBVA y los fixtures XML permanecen sin cambios por este bloque;
se conserva la aceptación «Formato de fichero correcto» documentada arriba.

## Artefactos privados

`data/finance/sepa/` está fuera de static, medios públicos y Git. Nombre aleatorio,
SHA-256, formato, fecha, número de transacciones y suma quedan en la BD. Una
exportación repetida devuelve el mismo artefacto; no sobrescribe el XML. Si falla
la transacción se eliminan solo los archivos nuevos de esa operación. Un corte
abrupto podría dejar un archivo huérfano no enlazado: su limpieza deberá ser
explícita, no automática. La descarga verifica el hash y usa `private, no-store`.

Las rutas se registran exclusivamente en la aplicación administrativa, bajo el
mismo perímetro de acceso que el resto de RentalManager. No se añade autenticación
independiente ni se publica ese servidor; la aplicación pública responde 404.
IBAN siempre enmascarado en tablas. Ni datos bancarios ni XML se añaden a URLs,
mensajes de error o logs de aplicación.

## Migración

`f8b0d2e4a671` sobre `e7a9b1c3d560` crea seis tablas privadas, sin backfill ni
semillas de negocio. No modifica tablas del ledger, BookingParty, mandatos o iCal.
El downgrade elimina estas tablas y solo se prueba en una copia: no utilizarlo
para volver atrás después de operar con remesas reales sin un plan de conservación.

Procedimiento: backup SQLite → ciclo aislado con guard de BD temporal → integridad
→ upgrade real → reinicio exclusivamente del servidor administrativo. La revisión
no requiere reiniciar sincronizador, web pública ni Cloudflare.
# Plan completo y trazabilidad de la Cuenta económica

La previsualización continúa siendo de solo lectura. Tras confirmar las condiciones,
el usuario revisa todas las mensualidades, decide si incluye la fianza y marca una
confirmación explícita antes de **Generar plan de cobros**. La operación crea y
contabiliza el calendario completo (`BookingCharge.posted`) en una única transacción
`BEGIN IMMEDIATE`, sin crear Payments. Los cargos futuros contabilizados representan
obligaciones previstas, no dinero recibido ni ingresos de caja. Así pueden ser
seleccionados posteriormente por Cobros según su mes de vencimiento, sin generar
deuda durante la creación de una remesa.

La repetición y las ejecuciones concurrentes no duplican el calendario. Una huella
del calendario revisado impide confirmar una previsualización desactualizada. Los
borradores existentes solo se contabilizan si coinciden exactamente; los distintos
requieren regeneración explícita y nueva revisión. Los cargos contabilizados nunca
se recalculan, sustituyen o eliminan desde esta acción. Cargos anulados o discrepantes
bloquean la generación y requieren revisar las correcciones. Se conservan los servicios
de borradores para compatibilidad, sin automatizar su regeneración.

Se mantiene una única renta por mes natural, con cambios de renta desde el primer
día de un mes y sin tramos intramensuales. Solo los extremos parciales de la estancia
se prorratean por días naturales. La UI sigue bloqueando múltiples versiones.

La tabla muestra un cargo por fila y sus aplicaciones explícitas (`PaymentAllocation`),
con enlaces a la remesa a través de sus Payment/return_payment, nunca por coincidencia
de importe o fecha. El histórico inverso enlaza cada pago con todos sus cargos.
Los cobros se suman y las devoluciones confirmadas se restan. Una devolución SEPA
conserva la secuencia y señala el saldo reabierto; si se cobra después, sigue visible
en el histórico pero no se presenta como una incidencia todavía pendiente.

Los estados de presentación no se guardan: borrador/anulado, cobrado (saldo cero),
parcial (cobro neto y saldo), vencido (fecha anterior a hoy), pendiente (vence hoy),
previsto futuro (vence después de hoy). Un parcial conserva también su situación de
vencimiento. Los abonos/correcciones se identifican separadamente. El resumen diferencia
previsión contractual según las condiciones y fechas actuales (incluida la fianza
pactada), plan realmente generado, contabilizado, aplicado neto, pendiente, vencido,
futuro y caja neta/sin aplicar. Una fianza pactada no genera automáticamente un cargo:
su inclusión en el plan sigue siendo una decisión explícita.

Los adeudos cobrados muestran `✓ Cobrado` en verde; los devueltos `! Devuelto` en rojo
con fila de incidencia y ambas fechas históricas. Las devoluciones solo se seleccionan
individualmente (se pueden marcar varias), sin opción de selección masiva.

Este ajuste no requiere migración adicional: conserva `a9c1e3f5b782`, no cambia el
exportador BBVA validado ni introduce nuevas tablas/estados persistentes.
