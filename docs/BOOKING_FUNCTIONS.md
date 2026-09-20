# Funciones de una persona en una reserva

- Nueva reserva manual: una sola Person, con `tenant`, `payer` y `occupant`
  seleccionados por defecto. Se exige al menos una función. Se conserva el flujo
  existente de alta de Person: no se fusionan identidades solo por nombre.
- Cada persona aparece una vez en el modal, con badges y edición múltiple.
  Añadir persona permite todas las funciones seleccionadas en una operación.
  Avalista sigue disponible. Desvincular exige confirmación y elimina todos los
  BookingParty de esa persona en esa reserva, sin eliminar su ficha.
- Actualización atómica mediante el límite transaccional SQLite ya existente
  (`BEGIN IMMEDIATE`): se conservan los IDs que no cambian; solo se insertan o
  eliminan diferencias. La restricción única por reserva/persona/función permanece.
  BookingParty no tenía histórico ni soft-delete; no se introduce uno nuevo.
- Las importaciones y datos legacy mantienen `unclassified`. No hay backfill.
  La reclasificación administrativa explícita sustituye Sin clasificar; no se
  combina con funciones conocidas. iCal no cambia su semántica.
- Cambiar responsables de pago con un mandato vinculado que ya no identifica a
  un pagador requiere confirmación de revisión y mantiene un aviso. No se borra
  el mandato, no se desvincula automáticamente ni se modifica información bancaria.
  Un titular bancario diferente sigue siendo posible: el aviso pide revisión,
  no presupone que el mandato sea inválido.
- Las operaciones de funciones no escriben en Booking, Person ni en el ledger.
  Cuenta económica sigue distinguiendo arrendatarios y responsables de pago.
- Sin migración: head `edf507b9c126`.

## Ficha de inquilino y navegación

- `Person.verification_status` es una marca administrativa (`unverified` /
  `verified`) introducida con Person en `a3c5e7f9b126`. No ejecuta verificación
  documental y ningún flujo de reservas, pagos, SEPA o publicación toma decisiones
  con ella. NetFincas solo inicializa nuevas personas como `unverified`.
- `birth_date`, `document_issuer_country` y `verification_status` dejan de
  aparecer o aceptarse en el formulario ordinario. No se eliminan sus columnas,
  los schemas internos ni los valores históricos. Guardar otros datos conserva
  los tres valores; no se convierte una ausencia de input en un borrado.
- Nacionalidad reutiliza `Person.nationality` (código de dos letras nullable).
  El formulario conserva la selección y la ficha muestra el nombre en español.
  El selector nativo admite teclado/búsqueda por escritura y una opción vacía;
  no añade una librería ni realiza llamadas externas en runtime.
- El catálogo local contiene los 249 códigos ISO 3166-1 alpha-2. Sus etiquetas
  se derivan de Unicode CLDR en español, consultado el 20-09-2026:
  https://github.com/unicode-org/cldr-json/blob/main/cldr-json/cldr-localenames-full/main/es/territories.json
  Se excluyen códigos reservados, supranacionales y extensiones no ISO. La
  licencia Unicode V3 se conserva en `backend/core/data/UNICODE-LICENSE.txt`.
- No se infiere nacionalidad desde domicilio, teléfono, IBAN o NetFincas. No hay
  backfill. Códigos legacy desconocidos se muestran como dato anterior y se
  preservan si no se cambian; las altas nuevas requieren un código del catálogo.
  Etiquetas legacy inequívocas del catálogo se pueden normalizar al guardarlas
  explícitamente. No se intenta adivinar gentilicios o textos ambiguos.
- Los nombres de Personas vinculadas abren `/persons/{id}`; se deduplican por
  identidad, no por nombre ni por número de funciones. Workspace, movimientos
  del Dashboard, barras del Gantt, cuenta económica, pago y configuración SEPA
  reutilizan ese criterio. El modal mantiene una fila enlazada por persona.
- Un nombre importado sin BookingParty permanece como texto: no se crea una
  persona ni un enlace artificial. Fechas/origen y el resto de la barra del
  Gantt conservan el acceso a la reserva. Los enlaces de personas no abren el
  modal; en Gantt el botón y los enlaces son hermanos, no controles anidados.
- Los DTO administrativos solo añaden id y nombre de la persona para construir
  los enlaces. No incluyen datos documentales, bancarios ni de contacto. No se
  modifica ningún DTO ni template público.
