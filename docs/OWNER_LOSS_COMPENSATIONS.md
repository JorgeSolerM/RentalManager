# Compensaciones documentadas de pérdidas — subfase 4.3

Estado: desplegado y verificado el 26/11/2026, tras aprobación del candidato. La subfase 4.2 de comisiones está descartada. No implementa la resolución económica de recuperaciones posteriores (4.4) ni componentes fiscales.

## Uso ordinario

Desde la incidencia, abrir «Aplicar compensación / Consultar compensaciones». Primero debe existir una pérdida reconocida con responsabilidad del propietario acreditada en 4.1. Asumir responsabilidad no equivale a autorizar su descuento: crear una autorización específica con referencia única del acuerdo, evidencia, importe y liquidaciones cerradas comprendidas en él. El propietario de esas liquidaciones debe ser el responsable, no el destinatario accidental.

La autorización requiere vista previa y aceptación expresa del permiso para compensar. No modifica saldos. Cada aplicación también requiere motivo, evidencia, vista previa y confirmación. Permite consumir el acuerdo parcialmente en operaciones sucesivas, sin superar su disponible ni el pendiente de cada liquidación.

La ficha de liquidación ofrece acceso al historial y a los acuerdos del propietario. Los estados distinguen pagos, compensaciones y combinaciones parciales o completas.

## Modelo y límites

`OwnerLossCompensationAuthorization`: incidencia, pérdida y operación de responsabilidad, propietario, referencia normalizada única del acuerdo completo, importe y alcance explícito de liquidaciones. Una autorización por pérdida y responsabilidad. En esta versión no se admiten acuerdos globales que cubran varias pérdidas o propietarios: no deben desdoblarse repitiendo su límite completo. No hay ampliación ni edición destructiva de autorizaciones.

`OwnerLossCompensationApplication`: autorización, liquidación del mismo propietario, importe, motivo, evidencia y auditoría inmutable. Los importes aplicado y disponible se calculan sumando aplicaciones; no existen contadores editables.

Ambas tablas conservan fecha UTC, operador disponible, huella de revisión, clave de idempotencia y estado económico revisado. Las referencias documentales son texto: no hay carga de adjuntos ni verificación automática de firmas. La aplicación no puede certificar la veracidad de documentos externos o detectar que dos referencias deliberadamente distintas describen el mismo documento; exige una referencia estable del acuerdo completo y bloquea su reutilización normalizada.

## Separación económica

Pendiente = importe del cierre − pagos válidos − compensaciones aplicadas.

Compensar no cambia fondos disponibles, dinero recuperado, salidas bancarias ni déficit. No inserta OwnerPayout, Expense, recuperaciones o líneas de liquidación. Falta de efectivo no impide una compensación válida; atribuciones desconocidas, devoluciones pendientes e incompatibilidades sí la bloquean. Se conserva la exclusión del circuito de facturación incompatible.

El payout ordinario continúa comprobando el menor entre pendiente y fondos disponibles. Su huella, la de correcciones y la de recuperaciones incorporan el historial de compensaciones. Una corrección administrativa de un pago calcula el pendiente incluyendo las compensaciones ya aplicadas.

## Recuperación posterior

La recepción real sigue permitida, incluso en varias recuperaciones. Se conserva el dinero recibido y su atribución. Si hay una pérdida compensada en esa incidencia, se muestra «Regularización posterior pendiente» y se bloquean conservadoramente las disposiciones del propietario compensado, también desde otras liquidaciones que compartan fondos. No se bloquea por este motivo a otros propietarios.

El bloqueo es por propietario, no una reserva limitada al importe recuperado: hasta la subfase 4.4 no hay una regla aprobada para separar la cantidad que debe restituirse o regularizarse. La vista previa de recuperación anticipa este bloqueo. No se deshace una compensación ni se inventa una obligación nueva. Nuevas compensaciones se bloquean también ante recuperaciones posteriores al reconocimiento pendientes de revisión.

## Documentos

El cierre, sus líneas y PDF anteriores permanecen intactos. Las nuevas versiones separan pagado, compensado y pendiente y muestran el acuerdo y la pérdida. Una liquidación posterior puede citar aplicaciones anteriores como información ya aplicada: esa cita no entra en sus totales ni consume de nuevo el acuerdo.

## Concurrencia y migración

Todas las escrituras revalidan bajo `financial_transaction` / `BEGIN IMMEDIATE`. Las claves idempotentes distinguen reenvíos de nuevas operaciones; la huella detecta cambios económicos después del preview. Dos claves diferentes no permiten exceder el saldo del acuerdo. Las restricciones de base de datos añaden unicidad, parentesco, identidad del propietario, alcance, límite acumulado e inmutabilidad.

Migración `5bc2d479ef34`, dependiente exclusivamente de `4ab1c368de23`: dos tablas, índices y seis triggers nuevos. No altera los triggers de OwnerPayout. Downgrade prohibido si hay historia. No usar stamp ni upgrade heads. El candidato original se comprobó sobre copia consistente. La preparación se probó exclusivamente con datos sintéticos, incluyendo un cierre preexistente y upgrade dirigido, sin migrar producción durante esa fase. El despliegue autorizado posterior se documenta al final.

## Verificación

Pruebas específicas: aplicaciones parciales, totales y sucesivas, duplicados, alcance y propietario, copropiedad, déficit, atribución pendiente, recuperación anterior/posterior, responsabilidades asignadas posteriormente, idempotencia, concurrencia con recuperación/payout, rollback, vistas previas obsoletas, HTTP real y campos ausentes, migración y documentos inmutables.

La batería consolidada incluye pérdidas, incidencias, recuperaciones, devoluciones, correcciones administrativas, liquidaciones, cálculo monetario y PDF. El manifiesto y el informe privado del candidato conservan los comandos, hashes, resultados e integridad. Los ejemplos y artefactos no son archivos para Git.

## Reanudación sobre la administración actual (2026-11-26)

Referencia `59e59ceb5f423d560d1ce90b55d86e2ab1966674`. Se recuperan los 21 archivos
del candidato previo (base `9bd2abcb3223f544a07a2dbe2285b568db3f66d7`) sin copiar sus
bases de datos. Se conservan los cambios pendientes de reutilización de inquilinos.
La única colisión de integración es la ficha de liquidación: mantiene sus controles
móviles y oculta el enlace a compensaciones cuando `request.state.admin_remote` es verdadero.
Se corrige también un anidamiento preexistente de la plantilla que ocultaba el
resultado económico local de la liquidación. El fallo se reproduce en el HEAD
y se verifica con el test original sin cambiar sus expectativas. Se conserva
la información actualmente visible en remoto, sin ampliar su exposición.
Las nuevas rutas de compensaciones siguen fuera de la lista de consultas remotas;
no se amplían permisos ni se modifica la autenticación.

Los formularios reutilizan el layout, navegación, estilos adaptativos y mecanismo
CSRF comunes. No hay JavaScript productivo ni dependencia nueva para esta subfase.
Las pruebas incluyen envíos nativos de autorización/aplicación y recarga desde
Playwright/Edge instalado opcionalmente, sin incorporarlo como dependencia de ejecución.

Reutilización revisada dentro de 4.3: normalización monetaria, evidencia segura,
idempotencia y huellas, transacción financiera, responsabilidad de pérdidas,
proyección de incidencias/recuperaciones, saldo de obligaciones y versionado PDF.
El servicio nuevo coordina autorización y consumo; no crea un segundo cálculo de
fondos. Los dos registros separados son necesarios para distinguir permiso y
aplicación y conservar auditoría inmutable. La proyección de compensaciones se
consulta por propietario; el formulario se consulta por incidencia para conservar
el caso de responsabilidad de otro copropietario. El saldo reutiliza esa misma
proyección ya calculada en las incidencias, evitando repetir tres consultas.
Esto es una revisión acotada de la subfase, no la auditoría integral futura.

## Procedimiento de despliegue y reversión

1. Revisar informe y manifiesto del candidato, hashes de base y trabajo ajeno.
2. Con ventana controlada de mantenimiento administrativo, respaldar de forma
   consistente SQLite y los archivos afectados; verificar lectura del respaldo.
3. Confirmar la revisión real previa `4ab1c368de23` y ausencia de divergencias.
   Si difiere, detenerse: no usar `stamp`, `head` ni `heads` para forzarla.
4. Tras autorización expresa, ejecutar únicamente `alembic upgrade 5bc2d479ef34`
   sobre el destino verificado. No aplicar `a01729dbe348`. Comprobar integridad,
   claves foráneas, tablas y triggers previos antes de instalar el código que usa
   las tablas nuevas. Desplegar solo el manifiesto revisado; excluir pruebas,
   evidencias, bases sintéticas y archivos ajenos.
5. Comprobar consultas locales y remotas, CSRF, bloqueos de escritura y PDF sin
   crear operaciones ficticias en producción. Si se necesita, reiniciar solo el
   servidor administrativo bajo autorización del despliegue.

Reversión inmediata antes de aceptar operaciones: restaurar el conjunto coherente
código/base respaldado. Si las dos tablas nuevas siguen vacías puede evaluarse el
downgrade dirigido a `4ab1c368de23`, probado en aislado. Si existe historial, el
downgrade destructivo se rechaza: detener escrituras y conservar toda operación
posterior; no restaurar una base antigua perdiendo movimientos. Requiere un plan
de reconciliación o corrección hacia delante. Toda reversión posterior debe preservar las operaciones registradas desde el respaldo.

## Cierre del despliegue — 26/11/2026

Se aplicó exclusivamente `4ab1c368de23 → 5bc2d479ef34`, sin rama fiscal.
La comparación transaccional conservó las 82 tablas y 1.737 filas anteriores;
los 97 triggers previos permanecen intactos y se añaden seis. Integridad SQLite
correcta, sin errores de claves foráneas y sin operaciones sintéticas en producción.
Se reinició únicamente el servidor administrativo; configuración Access, web
pública e iCal permanecen intactas. El código productivo coincide con el candidato.

Revalidación aislada: 163 pruebas superadas y los mismos tres fallos preexistentes
de Cache-Control; el test original de la ficha económica corregida pasa.
También pasa el flujo de navegador de autorización/aplicación en ocho resoluciones.
En producción se verificaron consultas, disponibilidad y rechazo de CSRF/JWT
inválidos sin crear movimientos. La autenticación Google/TOTP no se reconfiguró.
Los respaldos, hashes, comparación por tabla y resultados se conservan en el
informe privado del despliegue; no se incorporan bases ni credenciales al repositorio.
La subfase 4.4 y la auditoría integral siguen pendientes, sin iniciar.
