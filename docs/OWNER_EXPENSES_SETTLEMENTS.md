# Gastos y liquidaciones individuales

## Gastos por finca y proveedores

La creación ordinaria exige finca y fecha económica, no propietario. `owner_id`
vacío reparte el gasto mediante PropertyOwnership vigente en esa fecha. La UI
muestra el reparto como información; solo «A un propietario concreto» habilita
la selección excepcional. Quien soporta el gasto no es quien lo paga: este último
se registra en ExpensePayment. Una titularidad incompleta permite registrar un
gasto ordinario con advertencia, pero impide liquidarlo hasta resolverla.

Configuración → Proveedores (`/providers`) contiene el maestro privado Provider:
identificación fiscal y dirección estructurada, contacto, IBAN opcional validado
con la utilidad común, categoría habitual, notas, activo y timestamps. No aparece
en la navegación pública ni en sus consultas. El IBAN se muestra enmascarado en
ficha y solo completo en edición administrativa. La búsqueda admite nombre,
NIF/CIF y email. Se desactiva sin perder las relaciones históricas; el servicio
y la FK impiden borrar proveedores utilizados.

Expense.provider_id es opcional y la fuente estructurada principal; supplier se
conserva como fallback legacy, no como selector ordinario. La categoría del
proveedor es una propuesta editable. «+ Nuevo proveedor» abre un modal sin perder
el formulario del gasto. Cada gasto conserva provider_snapshot con nombre y
dirección fiscal al registrarse, sin IBAN ni notas: editar el maestro no altera
esa identificación histórica. Los futuros informes usarán Provider para agrupar
y el snapshot cuando necesiten identificación histórica.

La revisión `edf507b9c126`, sobre `dce4f6a8b015`, añade el maestro y los campos
opcionales de Expense sin backfill. Downgrade se bloquea si hay proveedores o
vínculos/snapshots para evitar pérdida de información. El despliegue requiere
backup y upgrade/downgrade/reupgrade aislado antes de migrar producción.

## Roadmap de informes y fases posteriores

- Informes económicos administrativos por periodo en PDF y XLSX real (no CSV
  renombrado), distintos del PDF de liquidación dirigido al propietario.
- Gastos: filtros fecha, finca, propietario, proveedor, categoría y estado de
  pago; columnas fecha, finca, proveedor, concepto, categoría, base, IVA,
  retención, total, pagado y pendiente.
- Ingresos: Payment + PaymentAllocation reales, nunca rentas teóricas; filtros
  periodo, finca, propietario, inquilino, concepto y método de cobro.
- Informe combinado ingresos/gastos/resultado por finca, propietario y periodo;
  XLSX con fechas, importes numéricos, filtros y totales.
- Reconciliación futura de los 132 proveedores NetFincas: matching conservador
  por NIF/CIF, nombre, contacto y cuenta cuando proceda, sin importación automática.
- Facturación fiscal de honorarios, PDF de factura, envío por correo, dashboard
  económico, honorarios fijos/mínimos y regularizaciones entre copropietarios.

Ninguna de estas fases futuras se implementa en este checkpoint.

## Límites del módulo

Todo es exclusivamente administrativo. No se envía dinero al banco. Registrar un
payout confirma una transferencia ya realizada fuera de RentalManager. No crea
Payment de Booking, remesas, facturas fiscales ni transferencias entre propietarios.

## Fuentes y caja

Solo Payment posted y PaymentAllocation alimentan ingresos. `rent` es inicialmente
liquidable y genera base de honorarios; los demás conceptos son conservadores
(ambas dimensiones desactivadas). SettlementChargePolicy permite configurar ambas
dimensiones por separado. No se usa Booking.price ni Room.base_price.

Un Expense se registra contabilizado, sin pago automático. Cada ExpensePayment es
un movimiento posted positivo: payment o reversal, con fecha y actor identificados.
El estado pendiente/parcial/pagado es derivado del neto. Los pagos parciales se
consumen independientemente por propietario. Los gastos impagados no se deducen.
Pagos adelantados por el gestor afectan sus fondos; pagos hechos por un propietario
afectan el resultado económico, no descuentan de nuevo fondos del gestor.

## Custodia y copropiedad

Cada OwnerSettlement corresponde a un Owner y puede incluir varias fincas. La
titularidad debe sumar exactamente 100 %. Se utiliza el periodo económico del cargo,
o expense_date en gastos. Los cambios dentro de un periodo requieren revisión:
no se inventa un reparto temporal. effective_until de PropertyOwnership conserva
su interpretación inclusiva; los periodos de cargos/liquidación son semiabiertos.

El primer cierre conserva el reparto de todos los propietarios para esa fuente;
el consumo único es (owner_id, source_key). Cerrar A no consume el derecho de B.
Las diferencias entre propietarios no bloquean el cierre ni crean deudas formales.

Ejemplo 500, 50/50 y A recibe todo: derecho 250 cada uno, directo A 500/B 0,
diferencia A +250/B -250, fondos del gestor 0 y payout por esos fondos 0.
Los honorarios se calculan sobre la parte económica de cada propietario.

Los cobros manuales se clasifican explícitamente en Custodia de cobros. SEPA usa
la cuenta receptora del grupo y comprueba que coincide con el snapshot bancario.
No se infiere por método. Si falta identificación se informa y no se cierra.

## Honorarios, versiones y devoluciones

Solo percentage_on_collected está habilitado. La versión corresponde al periodo
del cargo, no al día de cobro. Nueva versión cierra una vigencia abierta anterior
solo si no cambia periodos ya liquidados. Fijo/mínimo no están activados.
IVA y retención se configuran expresamente; no hay asesoramiento fiscal automático.
La base no se reduce por gastos: 1520 × 20 % = 304; con gasto pagado 104,54,
el resultado y fondos del gestor son 1111,46.

Las devoluciones mantienen movimientos originales. Antes del cierre se presentan
ambos y su neto; no se permite excluir solo uno para liquidar dinero ya devuelto.
Después del cierre, la devolución y reversión de honorarios aparecen como ajustes
nuevos con referencia original. Nunca recalculan una liquidación cerrada.

## Estados e integridad

- Expense: posted; la situación de pago se deriva. No edición destructiva de pagos.
- ExpensePayment: posted, dirección payment/reversal. No borradores de pagos futuros.
- OwnerSettlement: draft → closed; cancelled reservado. Cierre idempotente,
  fingerprint anti-stale y transacción BEGIN IMMEDIATE. Preview no escribe.
- OwnerPayout: posted, parcial/total según la suma. Nunca automático ni negativo.

Las líneas cerradas, payouts y pagos de gastos son inmutables mediante triggers en
la BD migrada. El cierre congela importes Decimal serializados como strings. Cada
fuente tiene FK explícita; el JSON conserva etiquetas, reparto y cálculo histórico.
Las cuentas payout conservan snapshot privado y se muestran enmascaradas.

Un saldo negativo se arrastra con referencia única al cierre anterior. El arrastre
no se suma dos veces al saldo global. Los payouts se limitan tanto al cierre como
a los fondos netos disponibles del Owner; devoluciones no liquidadas impiden pagar
un saldo histórico que puede haber dejado de existir.

## Uso y despliegue

La creación ordinaria parte del mes natural (por defecto el anterior) y de una
selección múltiple de fincas. PropertyOwnership resuelve los titulares actuales e
históricos; el servicio individual sigue atribuyendo cada movimiento a su periodo
económico. No hay selector obligatorio de propietario ni filtro adicional por ahora.
El catálogo diferencia listas, sin movimientos y pendientes de revisión. La acción
"Seleccionar todas" solo marca las listas. Ninguna aparece preseleccionada.

El preview desglosa finca/propietario y muestra el número de liquidaciones. Varias
fincas del mismo propietario se agrupan en un único borrador por selección: así el
saldo anterior se incluye una vez. Los subtotales de finca no incorporan ese saldo.
La creación del conjunto es atómica e idempotente; cualquier incidencia o cambio
desde el preview bloquea todo el conjunto. Crear borradores no consume fuentes,
no cierra liquidaciones ni crea pagos. Cada cierre sigue siendo independiente.
Se puede revisar y excluir líneas de una liquidación por separado antes de guardarla.

Rutas: /expenses, /settlements, /settlements/terms, /settlements/custody.
Se incluyen pendientes anteriores no consumidos de las fincas elegidas.
Excluir en preview no consume. Revisar selección antes de guardar el borrador.
Cerrar requiere confirmación y no crea payout.

Migración dce4f6a8b015 sobre cbd3e5f7a904: solo tablas nuevas, catálogo y políticas;
ningún backfill monetario. Downgrade rechaza actividad de negocio nueva.
El script scripts.seed_owner_economy_demo solo acepta una BD migrada, vacía y
distinta de producción. Utiliza exclusivamente datos sintéticos.

Fuera de alcance: fiscalidad completa, transferencias entre
propietarios, deducción automática del reparto durante cambios intraperiodo y
automatización bancaria de payouts.

## PDF de liquidación (incluido en este módulo)

Solo los cierres admiten PDF definitivo. `Descargar PDF de liquidación` genera o
recupera el artefacto; no cierra, contabiliza ni paga. A4 con cobros atribuibles,
gastos pagados, base/regla de honorarios, ajustes, custodia y resumen individual.
El documento es una liquidación, nunca una factura fiscal de honorarios.

Las cifras proceden de OwnerSettlement.snapshot y OwnerSettlementLine.snapshot,
sin recalcular Payment, Expense ni ManagementFeeTerms. Los nuevos cierres congelan
además emisor, propietario, nombres de fincas y referencias de inquilinos. Los
cierres anteriores sin identificación congelada la capturan al primer PDF; esta
procedencia queda en los metadatos, sin notas técnicas en el documento. No se
modifica el cierre ni se inventa identificación histórica.

Almacenamiento equivalente a los artefactos SEPA, sin nueva tabla: archivo PDF más
manifiesto JSON privado e inmutable por versión, en data/finance/settlements/{id}.
El manifiesto conserva settlement_id, tipo, versión, fecha UTC, filename seguro,
SHA-256 del PDF, hash de datos fuente y versión del renderer. La ruta es relativa
a la raíz privada. Se serializa con bloqueo portalocker y publicación atómica del
manifiesto; la descarga verifica nombre, confinamiento e integridad. No hay binarios
en BD ni montaje estático de esta carpeta. Está excluida de Git.

La misma información y versión del renderer devuelve el artefacto existente.
El renderer 2 utiliza tablas compactas, resumen y custodia condicional. Un cambio
de renderer genera una nueva versión documental conservando el hash de los datos
fuente y sin reemplazar los PDF anteriores. Pagos posteriores producen
otra versión con situación de pagos a fecha de generación; las versiones anteriores
siguen descargables en /settlements/{id}/documents/{version}. No se reescribe el
histórico económico. En copropiedad solo se emite la parte del propietario, sin
exportar el mapa interno de reparto de otros propietarios. Las cuentas de payout
solo muestran sus cuatro últimos dígitos.

La autorización de descarga utiliza el mismo perímetro administrativo de
RentalManager (servidor local, sin rutas en la aplicación pública), no un nuevo
sistema de login. Respuestas no-store/noindex, sin exposición en sitemap ni correo.
Las bases temporales usan su propia carpeta documental, separada de producción.

## Saldo individual a favor del gestor

Los fondos negativos se cierran normalmente: `payout_due` permanece a cero y
`manager_credit` expresa en positivo la deuda con el gestor. `carry_forward`
conserva el importe firmado. No se crea ningún OwnerPayout negativo.
El resultado del periodo se conserva separado en `period_balance`; el saldo
anterior se resta explícitamente para obtener `economic_balance` del nuevo cierre.
Los cierres anteriores permanecen inmutables, incluidos los de formato anterior.

El arrastre utiliza una línea `prior_balance` con FK `prior_settlement_id`,
individual por Owner y consumo único `(owner_id, source_key)`. El cierre se
serializa y revalida la preview; dos borradores no pueden consumir el mismo saldo.
Si el nuevo periodo solo absorbe parte de la deuda, el resto se arrastra desde el
nuevo cierre sin volver a consumir el antiguo. Se enlaza la liquidación de origen
para consultar los gastos, devoluciones o correcciones que explican el saldo.

La deuda con el gestor deriva de la custodia real: una diferencia entre
copropietarios o un gasto pagado por el propio propietario no se convierte por sí
solo en crédito del gestor. Los honorarios y adelantos pendientes sí se reflejan
en sus fondos. El cobro directo de deuda al propietario queda para una fase futura;
no se incorpora OwnerPayment. No requiere migración ni backfill.

## Fase posterior: Envío de liquidaciones a propietarios

OwnerSettlement cerrado → PDF → acción explícita Enviar por correo. Configuración
SMTP/proveedor propia de RentalManager, nunca Mailbird. Registrar destinatario,
fecha/hora, documento/versión/hash, resultado, error y reintentos idempotentes.
No enviar automáticamente ni habilitar envíos sin configuración. Envío masivo queda
para otra fase. Detalle de honorarios y factura fiscal serán tipos documentales
separados, sin reutilizar este PDF como factura. No se implementa correo en este bloque.
