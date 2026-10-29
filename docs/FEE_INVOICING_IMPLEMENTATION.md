# Honorarios: liquidación, compensación y factura de prueba

## IMPLEMENTADO

Base publicada tras el desacoplamiento: `11976ad015627cd5232199ed7aecf24371f3cde8`
(Finalización anticipada). Cadena vigente:
`fe0618cad237 -> b1283aedf459 -> a01729dbe348`.
Facturación sigue pendiente de commit. Producción conserva el marcador
`b1283aedf459`, aunque contiene las 17 tablas fiscales vacías del despliegue
privado anterior. No se ha migrado producción durante la recuperación de octubre.

Circuito integrado: periodo y fincas → preview agrupado → elección de gastos
ambiguos/fechas fiscales → borradores → cierre en orden propuesto → preview de
factura → borrador sin número → emisión sintética → PDF A4.

### Agrupación y snapshots

`SettlementSelectionService` delega en `BillingSettlementService` con el flag de
pruebas. Agrupa Owner + periodo + contenido de `fee_signature_v1`, no Terms.id.
El único algoritmo es `group_fee_sources` en `fee_grouping.py`, utilizado también
por el flujo integrado. `BillingSettlementService` resuelve datos y condiciones
históricas, llama al planificador común y aplica su resultado; no reagrupa por su
cuenta. Las fincas con solo gastos/ingresos sin honorario aportan una firma fiscal
explícita de respaldo. Las asignaciones ya consumidas se excluyen al revisar el
siguiente borrador, sin volver a consumir la fuente.
Porcentaje, IVA, retención, tratamiento, motivo, régimen, moneda y redondeo forman
parte de la firma. Fuentes/fincas permanecen separadas. Distintos IDs con el mismo
contenido son homogéneos; menciones libres se congelan sin dividir por redacción.

Las condiciones se resuelven por periodo económico de renta, también en cobros
atrasados. El honorario se genera al cerrar el cobro efectivo. La fecha fiscal se
configura como fecha de cobro o fecha explícita por fuente, nunca cierre implícito.

Gasto con un único grupo candidato: asignación automática. Varios grupos de esa
finca: elección explícita. No reparto por porcentaje de honorarios ni duplicado.
El endpoint legacy de borrador individual no permite eludir esta agrupación.

Cada línea de liquidación congela base, IVA, retención, neto, porcentaje,
tratamiento, motivos/menciones, moneda, redondeo, mapping, firma, periodo económico,
cobro/operación fiscal, finca y condiciones de origen. Las devoluciones conservan
el tratamiento original y revierten cuotas exactas, sin tasas actuales. La factura
copia estos snapshots y el nombre de finca congelado, sin reconstrucción viva.

### Custodia y compensaciones

Nuevos cobros manuales, Payment draft contabilizados y SEPA registran custodia del
gestor en su transacción. Sin backfill. Excepciones de custodia directa legacy se
conservan, no se ofrecen como flujo ordinario nuevo.

`FeeObligation` identifica gasto adelantado, honorario o ajuste; `FeeFund` su
fuente; `FeeCompensation` la aplicación parcial. Ajustes/reversiones son nuevas
filas. Prioridad: antigüedad, gastos antes de honorarios a igual fecha, desempate
estable. Fondos y obligaciones individuales por Owner.

Preview simula grupos sucesivos. Cierre serializado comprueba el estado real de
obligaciones contra el esperado. Cerrar el segundo grupo antes del primero exige
revisión; nunca consume un saldo solo simulado. Cambios concurrentes invalidan
borradores. Aplicaciones cerradas no se modifican por el servicio aislado legacy.

300 cobrados / 500 adelantados / 60 honorario: aplica 300 al gasto, pendientes
200 + 60, payout cero. Otros 500 sin nuevos honorarios recuperan 260 y dejan 240.
No crear otra deuda por remanente ni editar liquidaciones históricas.

### Configuración, identidades y factura

Configuración → Facturación: emisor/versiones, identidad fiscal Owner, series,
fiscalidad por versión de honorarios y estado VERI*FACTU. IVA general explícito:
repercutido, exenta, no sujeta por localización/otra causa e inversión. Retención
separada. No inferir exención de IVA cero. IGIC/IPSI/recargo/regímenes especiales
rechazados inicialmente. Vigencia heredada de la versión de honorarios.

Owner conserva nombre/domicilio; `OwnerFiscalIdentity` añade tipo/país documental,
sin inferencias desde IBAN. Datos incompletos: preview con aviso, emisión bloqueada.
Validación local de presencia/formato, no acreditación censal ni residencia fiscal.

Una F1 ordinaria completa por liquidación cerrada, no parciales/simplificadas.
`ManagementFeeInvoiceLine` y `ManagementFeeInvoiceSource` preservan finca y origen.
Preview/borrador no consumen número. Borrador desactualizado solo se reemplaza tras
una nueva revisión explícita, antes de emitir.

Emisión serializada: revalidación, UPDATE RETURNING del contador, factura, líneas,
fuentes, registro, cadena y outbox en una transacción. Fallo revierte contador.
Concurrencia/doble clic/retry: una factura. Series usadas no retroceden contador
ni cambian identidad. Índice NIF emisor + número impide duplicados entre versiones
de perfil. La UI impide repetir prefijo para un NIF; fecha no retrocede por serie.

Triggers SQLite protegen facturas emitidas, líneas/fuentes, registros fiscales e
histórico de compensaciones contra UPDATE/DELETE. Cambiar datos actuales no
reescribe documentos. Base + IVA = bruto fiscal; base + IVA − retención = neto.
Registro/QR usan bruto. Generado/compensado/pendiente/facturado se muestran separados.
Emitir no crea Payment ni otra compensación.

### VERI*FACTU, XML, PDF y correcciones

Cadena por obligado/SIF/instalación/entorno, no por Owner, finca o serie. SHA-256
contrastado con vectores oficiales. Outbox test e intentos/resultados persistentes;
mocks desconocido/reintento/aceptado/rechazado sin segunda factura. Sin transporte.

Serializador XML F1 local: estructura oficial, cuotas congeladas, agrupación del
desglose fiscal sin perder líneas, NIF/IDOtro, cadena y SIF. XML sintéticos
contrastados localmente con XSD oficiales. No equivale a aceptación por AEAT.

PDF privado A4, QR 34 mm/nivel M con endpoint de pruebas, marca SIMULACIÓN SIN
VALIDEZ FISCAL / NO REMITIDA. PDF no es fuente del hash fiscal.

Devolución liquidada de honorario facturado crea `InvoiceRectificationNotice`;
original inmutable, factura ordinaria negativa bloqueada. Campos de referencia
rectificativa preparados, sin flujo de emisión rectificativa en esta fase.

## NO HABILITADO EN PRODUCCIÓN

`INVOICING_ENABLED=false`, `VERIFACTU_ENABLED=false`,
`VERIFACTU_SUBMISSION_ENABLED=false`. El último no se puede activar todavía.
El guard exige `INVOICING_SYNTHETIC_DATABASE` coincidente con la conexión y rechaza
la BD real/alias. Configuración, cierres fiscales y emisión de prueba están
restringidos a esa BD; activar solo un flag no permite emitir en producción.

La nueva custodia de cobros ordinarios no depende del flag de facturación;
es parte expresa de este checkpoint. La emisión/configuración fiscal sí está
restringida al entorno sintético.

### Reconocimiento posterior seguro de la migración

1. Con autorización posterior, obtener un backup SQLite consistente y privado,
   comprobar `quick_check`, `foreign_key_check` y marcador `b1283aedf459`.
2. Ensayar `upgrade a01729dbe348` sobre una copia, con `DATABASE_URL` apuntando
   exclusivamente a ella y `ALEMBIC_REQUIRE_TEMPORARY_DATABASE=1`.
3. La revisión verifica tablas, columnas, restricciones/FK, índices y triggers
   mediante la firma DDL SQLite esperada. Si faltan tablas o existe cualquier
   divergencia, aborta y exige revisión; no se usa `stamp`.
4. Comparar esquema completo y huellas de las filas de todas las tablas antes y
   después. Con el esquema privado exacto solo debe cambiar `alembic_version`.
5. Solo tras autorización de producción repetir el upgrade dirigido y comprobar
   integridad/recuentos. NO se ha ejecutado sobre la BD real en esta recuperación.

Una instalación limpia crea las 17 tablas tras `b1283aedf459`. El downgrade a
esa revisión se bloquea si alguna tabla fiscal contiene datos. Los backups del
antiguo orden privado deben restaurarse con su código correspondiente y auditarse;
no se deben reinterpretar sus marcadores mediante un stamp automático.
No reiniciar iCal ni crear ejemplos en producción.
Backups/runtime/PDF/XML quedan fuera de Git; `output/pdf/` está ignorado.

## Escenarios sintéticos

Base de revisión: `http://127.0.0.1:8119`, nunca producción.
Recuperado el 29/10/2026 con una BD nueva creada mediante Alembic desde cero hasta
`a01729dbe348` (no `metadata.create_all`). Datos exclusivamente sintéticos. Los
ejemplos cerrados/emitidos son fixtures preparados mediante servicios; el flujo
J permanece abierto para las confirmaciones manuales del usuario.

| Caso | Ruta | Contenido |
|---|---|---|
| Configuración | `/settings/invoicing` | Emisor, series, fiscalidad, VERI*FACTU |
| A | `/settlements/1`, `/invoices/1` | Cobro 1520; base 304; IVA 63,84; retención 45,60 |
| B | `/settlements/2`, `/invoices/2` | Dos fincas homogéneas, líneas separadas |
| C | `/settlements/3`, `/settlements/4` | 20/15 %, dos facturas |
| D | `/settlements/5/invoice?series_id=1&issue_date=2026-09-30` | Agosto 15 % cobrado septiembre; preview |
| E | `/settlements/6` | 300/500/60; pendientes al cierre 200 + 60 |
| F | `/settlements/7` | Recuperación 260; disponibles 240 |
| G/H | `/invoices/1` | Sin duplicado; identidad histórica conservada |
| I | `/settlements/8`, `/invoices/1` | Devolución y rectificación pendiente |
| PDF | `/invoices/2/pdf` | Dos fincas, documento sintético |
| Manual | `/settlements/new?month=2026-09` | Finca J, confirmaciones reservadas al usuario |

E conserva su cierre; su resumen actual refleja la compensación posterior en F.
F usa 500 EUR de ingresos sintéticos expresamente excluidos de la base de nuevos
honorarios: compensa primero 200 de gastos y después 60 de honorarios, quedando
240. A conserva su factura original; I añade posteriormente su devolución y el
aviso de rectificación, sin reescribirla. C muestra primero 15 % y después 20 %
según el orden estable del planificador, no según el ID de las condiciones.
Las facturas se consultan desde cada liquidación; no existe aún un listado
independiente en `/invoices`.
Los IDs identifican solo fixtures locales. No automatizar confirmaciones manuales.

## PENDIENTE DE VALIDACIÓN FISCAL/AEAT

- Revisión profesional de tratamientos, menciones, criterio de operación y datos
  censales. RentalManager no determina el régimen fiscal del usuario.
- Validación real del perfil completo en AEAT, semántica/respuestas, transporte
  autorizado, almacén seguro de certificados y operación productiva de la cola.
- Rectificativas/subsanaciones/anulación completas, fuera de esta fase.
- Declaración responsable del productor/sistema/versión/instalación y alcance
  validado. No se declara cumplimiento VERI*FACTU completo.

No guardar certificados/contraseñas en tablas ordinarias, Git, fixtures o logs.
Futura integración mediante referencias a secretos en almacén seguro del sistema.

## PROBADO SINTÉTICAMENTE: recuperación del 29 de octubre de 2026

- Copia consistente de producción: upgrade compatible; solo cambia el marcador
  a `a01729dbe348`. Esquema completo y huellas de filas idénticos antes/después.
- Integridad de la copia: `quick_check=ok`, `foreign_key_check` limpio.
- Escenarios A-I regenerados con las rutas anteriores; cinco facturas sintéticas
  y sus PDF. No se han utilizado certificados ni enviado registros.
- Tests de agrupación: llamada del servicio al planificador común, firmas
  inválidas, gastos sin ingresos y fuentes sin honorario.
- 24 comprobaciones HTTP de configuración, liquidaciones, preview, facturas y
  PDF: todas 200. Vistas revisadas en navegador a 375/768/1280 px, sin overflow
  horizontal del documento ni errores de consola. Selección y preview manual
  comprobados sin guardar/cerrar/emitir mediante la interfaz.
- Cinco PDF de una página generados y revisados mediante renderizado; cinco XML
  nuevos validados contra los XSD locales, con resolución offline sin acceso a
  AEAT. Cero intentos de remisión.
- Producción consultada en solo lectura: marcador `b1283aedf459`, integridad
  correcta y las 17 tablas fiscales vacías. `/settings/invoicing` devuelve 404
  en la administración productiva; no se ha reiniciado ni habilitado el módulo.
- Batería consolidada actual: **663 passed, 1 warning**, 1342,31 s, 55 archivos
  Python. Incluye facturación, custodia, compensaciones, liquidaciones, migraciones,
  reservas/finalización anticipada, SEPA, NetFincas, iCal y privacidad pública.
  Aviso: deprecación de Starlette TestClient/httpx, no fallo funcional.
- JavaScript de finalización anticipada: **7 passed**. Resultado separado, sin
  sumar las ejecuciones enfocadas solapadas. `git diff --check` correcto.

## VALIDACIÓN FUNCIONAL Y VISUAL APROBADA

El usuario ha aprobado los escenarios A-I, configuración, PDF y compensaciones.
El checkpoint se consolida únicamente en Git local, sin push ni despliegue.
No se han automatizado los diálogos reservados a la revisión manual.
Esta aprobación no habilita producción ni acredita integración/conformidad AEAT.

## Seguimiento operativo fuera del checkpoint

El 29/10/2026 se observó un timeout aislado de iCal durante la auditoría:
63 calendarios correctos, 2 warnings, 1 error y 13 sin importación. Queda
registrado para seguimiento independiente en ejecuciones ordinarias posteriores.
No se ha atribuido a facturación ni modificado/reiniciado el sincronizador;
no se incluyen URLs privadas ni contenido de feeds en esta documentación.
En la lectura posterior de cierre: 63 ok, 3 warnings, 0 errores y 13 sin
importación. El timeout ya no aparece como error; conservar el seguimiento sin
dar por explicada la causa ni forzar nuevas sincronizaciones.

## Referencia histórica (20 de septiembre de 2026; no es el estado actual)

- Batería consolidada: **530 passed, 1 warning**, 1259,83 s. Incluye custodia,
  honorarios/facturación/compensación, migraciones y regresión financiera, SEPA,
  liquidaciones, NetFincas, privacidad pública e iCal. La comprobación enfocada
  adicional de 65 tests se solapa; no se suma al total consolidado.
- En aquel despliegue privado: migración real `a01729dbe348`, después de backup y ciclo aislado.
  Comparación antes/después inmediata: registros de negocio idénticos. Las 17
  tablas nuevas están vacías; no se han creado perfiles ni series reales.
- `quick_check=ok`; `foreign_key_check` sin resultados.
- Datos reales: 62 Bookings, 64 Persons, 62 BookingParty, 76 Guests y 2 Owners.
  Ledger, gastos, liquidaciones, remesas y artefactos económicos: cero.
- iCal: 64 ok, 2 warning, 0 error, 13 sin importación; no se ha reiniciado.
- Navegación sintética: 30 vistas HTTP 200, H1 único y sin overflow del documento
  a 375/768/1280. Selección → preview también comprobada en esos tres anchos,
  sin pulsar guardar/cerrar/emitir ni aceptar confirmaciones.
- Sin excepciones JavaScript; permanece el 404 preexistente de `/favicon.ico`.
- Cinco XML sintéticos válidos contra los XSD oficiales en comprobación offline.
- Producción y web pública continúan HTTP 200, sin reiniciar sus procesos.
  Validación manual final de las confirmaciones reservada al usuario.

Fuentes oficiales: [hash v0.1.2](https://www.agenciatributaria.es/static_files/AEAT_Desarrolladores/EEDD/IVA/VERI-FACTU/Veri-Factu_especificaciones_huella_hash_registros.pdf),
[QR](https://www.agenciatributaria.es/static_files/AEAT_Desarrolladores/EEDD/IVA/VERI-FACTU/DetalleEspecificacTecnCodigoQRfactura.pdf),
[validaciones](https://www.agenciatributaria.es/static_files/AEAT_Desarrolladores/EEDD/IVA/VERI-FACTU/Validaciones_Errores_Veri-Factu.pdf),
[XSD](https://prewww2.aeat.es/static_files/common/internet/dep/aplicaciones/es/aeat/tikeV1.0/cont/ws/SuministroLR.xsd).
