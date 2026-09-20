# Categorías de gasto

Configuración → Proveedores contiene dos pestañas: Proveedores y Categorías de
gasto. Gastos continúa como módulo independiente en `/expenses`.

Proveedores muestra únicamente Proveedor | Predeterminada | Activo. El nombre
dispone del ancho restante y puede envolver, enlazando a la ficha completa;
los datos fiscales, contacto e IBAN no se muestran en la tabla. El switch usa
rm_switch y el mismo controlador de guardado/toast/reversión que Categorías.
Un proveedor inactivo sigue siendo navegable, con nombre y categoría atenuados.
Los formularios y la ficha conservan todos los campos existentes.

## Catálogo único

Se reutiliza `ExpenseCategory` y las FK existentes de `Expense.category_id` y
`Provider.default_expense_category_id`. No se crea un catálogo paralelo.
Las ocho categorías existentes conservan ID, código y nombre: Limpieza,
Reparación, Suministros, Comunidad, Seguro, Impuestos / tasas, Mantenimiento y Otros.
No se añaden categorías iniciales ni se reclasifica ningún gasto.

El administrador puede crear, renombrar, describir, ordenar y activar/desactivar.
El código interno permanece estable; las nuevas categorías usan un identificador
opaco. Los nombres equivalentes por espacios, mayúsculas o acentos se rechazan
también cuando la categoría existente está inactiva. La comprobación y escritura
son transaccionales (BEGIN IMMEDIATE), sin carreras entre altas administrativas.
No hay operación de borrado, incluso para categorías sin uso.

Listado compacto: Categoría | Orden | Activa. El nombre enlaza a edición de
nombre, descripción y orden; editar no altera el estado. Se reutiliza rm_switch
para activar/desactivar inmediatamente, sin confirmación, con toast y estado
accesible. Un fallo revierte el control; las filas inactivas conservan nombre
enlazable y orden en texto secundario. La descripción no aparece en el listado.

Orden: número ascendente, valores sin orden al final, nombre e ID como desempate.
Proveedores y Gastos consultan la misma ordenación. Las categorías inactivas se
conservan en el histórico con la etiqueta Inactiva, pero no son nuevas opciones.
Editar un proveedor permite mantener su categoría ya inactiva, no asignársela a
otro. El formulario de gasto solo propone la categoría habitual si sigue activa;
permite cambiarla sin alterar el proveedor. El proveedor continúa siendo opcional.

La etiqueta visible es «Categoría de gasto predeterminada», opcional. El formulario
de gasto distingue propuesta automática de elección manual únicamente en memoria:
un cambio de proveedor puede reemplazar una propuesta aún no editada, nunca una
selección manual no vacía. Quitar proveedor o elegir uno sin categoría activa no
vacía ni altera la categoría actual. Un campo vacío puede recibir una propuesta.
Los valores devueltos tras un error de validación se protegen como elección manual.
Pruebas frontend sin dependencias: `node --test tests/frontend/expense_category_autofill.test.cjs`.

## Migración

`fe0618cad237`, sobre `edf507b9c126`, añade exclusivamente description, sort_order,
created_at y updated_at mediante ADD COLUMN, sin reconstruir la tabla referenciada.
Los metadatos descriptivos/orden quedan NULL. Las fechas de las categorías existentes
indican inicio del seguimiento del catálogo en la migración, no su creación histórica.
Las escrituras ORM nuevas generan las fechas y actualizan updated_at.
No hay backfill económico, proveedores nuevos ni categorías nuevas.

Upgrade/downgrade/reupgrade se valida en copia aislada antes de la BD real, con
backup SQLite consistente e integridad. El downgrade conserva categorías, códigos,
FK e históricos y se bloquea si hay descripción u orden que se perderían.

## Fuera de alcance

No se cambian pagos, liquidaciones, IBAN, iCal, importaciones ni la web pública.
Las pestañas nuevas se muestran cuando el proceso ha cargado el router actualizado;
las plantillas compartidas no anuncian rutas nuevas a un proceso antiguo pendiente
de recarga. La revisión manual se realiza en el servidor sintético independiente.
La futura reconciliación será Proveedor NetFincas → Provider → ExpenseCategory,
con revisión explícita y sin importación histórica en este checkpoint.
