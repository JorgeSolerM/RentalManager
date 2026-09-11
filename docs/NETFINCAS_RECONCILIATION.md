# Reconciliación administrativa NetFincas

Herramienta opt-in de revisión, dry-run y aplicación selectiva. No importa recibos históricos, cargos, pagos ni mandatos. La fuente Firebird se copia a un directorio temporal y se consulta en transacciones de solo lectura mediante una instalación compatible de `isql`. Nunca se conecta a producción NetFincas.

## Activación

Por defecto está deshabilitada. Variables del proceso administrativo:

- `NETFINCAS_RECONCILIATION_ENABLED=1`.
- `NETFINCAS_SOURCE_DATABASE`: copia privada Firebird autorizada.
- `NETFINCAS_ISQL`: ejecutable compatible privado.
- `NETFINCAS_APPLY_DATABASE`: ruta absoluta exacta de la SQLite autorizada para aplicar. Si no coincide, solo se permite revisar.

La revisión `cbd3e5f7a904`, sobre `bac2e4f6d893`, crea únicamente `migration_runs` y `migration_actions`, sin backfill. Debe aplicarse antes de habilitar el módulo, tras backup verificado y ciclo aislado con `ALEMBIC_REQUIRE_TEMPORARY_DATABASE=1`. Migrar no activa la herramienta ni importa datos. El downgrade se rechaza si existe trazabilidad, para evitar destruirla.

## Flujo y límites

Ruta `/reconciliation/netfincas`. Pestañas de resumen, inquilinos, contratos, fincas, propietarios, SEPA y conflictos. No hay selección automática ni importación global.

Flujo visible: **Seleccionar → Revisar cambios → Confirmar → Aplicar cambios**. Todos los registros y campos empiezan sin seleccionar. El filtro «Datos completables» se limita a personas con coincidencia fuerte y contexto vigente; no incluye una posible prórroga como único contexto. Los nombres y la finca/habitación preceden a las referencias técnicas.

La comparación de inquilinos se actualiza al elegir destino; durante la consulta los campos quedan deshabilitados. Los campos no vacíos no son seleccionables para sobrescritura. El IBAN de una persona existente requiere coincidencia fuerte con ese destino. La creación de una identidad con candidatos exige confirmación adicional explícita de que es distinta. Los propietarios admiten completar campos seleccionados, omitiendo los ya informados. Las cuentas son operaciones separadas con titularidad confirmada.

Revisar cambios muestra destinatarios, valores enmascarados, recuentos, acciones omitidas y lo que no se modificará. Volver a seleccionar inicia una revisión nueva (sin conservar casillas). No hay actualización de fechas de reservas existentes; una alta muestra sus fechas y renta candidata sin importar esta última automáticamente.

Las puntuaciones son heurísticas explicadas por evidencia (documento, email, teléfono, IBAN, nombre y contexto de estancia), no probabilidades. Un nombre aislado no produce coincidencia fuerte. Los candidatos requieren revisión humana.

Teléfonos: la capa común `phone_candidates` utiliza `PHONE_MAPPINGS` por entidad. Se verificaron los formularios instalados: inquilinos y propietarios usan `edMovil.DataField=FAX`; la ficha histórica también etiqueta FAX como Movil. TEL es Teléfono. El adaptador marca la entidad de origen y no duplica FAX como tercer número. Concepto visible: Móvil NetFincas; campo físico solo como detalle técnico/auditoría.

Contactos conserva TELEFONO, MOVIL y FAX separados; Empresa usa TELEFONO/FAX; Proveedores TELEFONO1/TELEFONO2/FAX. Los fax reales no se convierten automáticamente en teléfonos. Estos mappings comunes no habilitan importaciones de nuevas entidades. ALQ_INMUEBLES contiene teléfonos de avalistas y ALQ_EXPEDIDOR teléfonos de representante/contacto: son personas/roles diferentes, no se mezclan con inquilino ni propietario. No hay teléfonos en las tablas auxiliares de propietarios auditadas; ADMINISTRACION no aporta un contacto personal reconciliable.

Propietarios reutiliza validación, normalización, detección de números distintos y elección explícita. Su selector empieza vacío en conflicto, y un destino con teléfono informado queda protegido tanto en UI como en plan/aplicación. La selección de origen es un identificador de campo validado contra la fuente privada, nunca un teléfono proporcionado por el navegador. La creación de propietario sigue limitada a identidad, sin añadir teléfonos silenciosamente.

Prioridad conceptual: Móvil, Teléfono, FAX legacy, siempre con sintaxis plausible. Cuando hay números válidos distintos, «Revisar teléfono» ofrece un selector inicialmente vacío. La elección explícita se valida contra la fuente privada, no contra un número enviado por el navegador. Solo entonces se habilita completar phone si el destino está vacío; no hay sobrescritura. Un campo prioritario inválido también exige elección explícita. Separadores y 00/+ se normalizan solo para comparar, sin inferir país; al guardar se usa la normalización de espacios de PersonService. La plausibilidad no prueba existencia ni titularidad.

Otros enlaces verificados en el formulario: APEYNOM (nombre), NIF, DIRSIGLA (edSigla), DIR (nombre de vía), DIRNUM (número/bloque/portal/escalera), DIRPISO (planta), DIRLETRA (puerta), CP, POB (municipio), PROVINCIA, MAIL. No existe DIRNOMBRE en esta copia: el nombre de vía está en DIR. IBAN contiene el prefijo y se completa con los segmentos bancarios existentes; se mantiene la validación de checksum.

Dirección: Person.address_line conserva la sigla literal, calle y número, con planta/puerta identificadas cuando existen. CP, municipio, provincia y país permanecen en sus campos independientes. No se expanden siglas ambiguas o extranjeras. Los componentes originales se muestran en comparación y se referencian mediante la huella de la fuente privada, sin copiar direcciones al registro persistente de auditoría.

PAIS es un dato no fiable y exclusivamente informativo. No pertenece a los campos importables, no genera candidatos, no interviene en matching/scoring ni en Datos completables. La UI no ofrece checkbox y el backend rechaza selecciones manipuladas y planes antiguos que contengan country, antes de escribir. No se normaliza ni infiere país de PAIS, teléfono o IBAN. Los países ya guardados no se corrigen automáticamente: cualquier reparación necesita autorización separada y trazabilidad, conservando la importación original.

La revisión muestra todos los valores originales y su origen. Para una futura actualización de phone, MigrationAction conserva el ID fuente y el campo elegido (por ejemplo, `person:101:FAX`), y el digest del origen permite referenciar el original conservado en la copia privada. El original también figura en la revisión en memoria; no se vuelca en logs ni se añade una copia del número al registro de auditoría. Nunca se sobrescribe un teléfono informado ni se aplica sin selección y confirmación.

Solo se completan campos vacíos seleccionados. No se sobrescriben datos. Las nuevas personas no reciben roles contractuales inferidos. Las nuevas reservas requieren habitación/persona explícitas y confirmación de la semántica de fin exclusivo; su vínculo inicial es `unclassified`.

Una posible prórroga es únicamente una clasificación de revisión: no cambia fechas. Los términos económicos se crean exclusivamente en draft desde RENTA y FIANZA_IMPORTE, con confirmación contextual y vencimiento explícito. No se generan cargos ni pagos.

Fincas, participaciones y candidatos SEPA se presentan para revisión, sin crear relaciones ambiguas ni mandatos. Las cuentas de propietario requieren confirmación explícita del titular y no se habilitan automáticamente para rentas/liquidaciones.

## Seguridad y trazabilidad

Los planes permanecen en memoria durante 15 minutos y se invalidan al reiniciar. Cookie HttpOnly/SameSite, comprobación CSRF y respuestas no-store. IBAN enmascarado en la revisión y dry-run. No hay valores bancarios en el registro de auditoría.

Aplicación transaccional con bloqueo SQLite, comprobación de huellas de origen/destino y claves idempotentes. Un fallo revierte toda la selección. La auditoría conserva origen, destino, operación/campo, resultado y fecha; no copia valores personales. Un destino modificado exige construir otro dry-run.

Los backups, fuentes Firebird, credenciales, informes privados y bases de demostración permanecen fuera de Git. Los tests utilizan únicamente datos sintéticos.
