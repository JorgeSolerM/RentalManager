# Inicio de gestión económica por reserva

## Estado y alcance
Implementado, probado en copia aislada y desplegado con autorización el 19/11/2026. Validación visual aprobada para cierre en Git. No afecta ocupación, Person/BookingParty ni fechas contractuales. No genera pagos, remesas o liquidaciones al configurar el inicio.

Booking incorpora economic_management_start (fecha opcional) y economic_management_start_configured_at (UTC). Sin configuración se conserva el comportamiento anterior: contrato completo. No existe backfill. La UI propone el mes de entrada y exige confirmación para guardar la configuración. Para revisar importes exige una sola versión confirmada de condiciones.

## Revisión y confirmación
Cuenta económica → Mes de inicio → Revisar inicio de gestión → revisar incluidos, excluidos, fianza y cargos existentes → confirmar y guardar.
El mes debe empezar el día 1, desde el mes de entrada y antes de la salida económica exclusiva. El cálculo original se realiza completo y después se filtran las mensualidades anteriores: no se desplaza la entrada ni se inventa un prorrateo en el mes de inicio contable. Los meses excluidos son informativos, no se consideran pagados ni pendientes. Las claves de generación permanecen intactas. La fianza anterior al inicio queda informativa, fuera de generación automática.

Se bloquea ante cargos posted/void, pagos, allocations, consumos de liquidaciones o adeudos vinculados. Los borradores manuales afectados bloquean; solo se retiran borradores reconocidos del plan automático y con aceptación expresa. Los borradores posteriores se conservan. No se cambia ninguna liquidación cerrada.
La confirmación revalida una huella del estado dentro de BEGIN IMMEDIATE. Un cambio concurrente exige otra revisión. Repetir la misma confirmación no vuelve a consumir ni borrar nada. La revisión de finalización anticipada aplica también el límite contable; su huella incluye la configuración.

## Migración independiente y despliegue controlado
Producción migrada exclusivamente de b1283aedf459 a c2394bfe056a. La revisión fiscal a01729dbe348 sigue pendiente y no se modifica.
Nueva rama: fe0618cad237 → b1283aedf459 → c2394bfe056a (economic_start).
El código mantiene DOS heads intencionados: a01729dbe348 y c2394bfe056a. No usar upgrade head/heads indiscriminadamente ni stamp. Se ha probado upgrade c2394bfe056a, downgrade b1283aedf459 y upgrade c2394bfe056a sobre copia consistente de producción, sin cambios en registros existentes. La revisión solo añade dos columnas nullable y dos triggers de validación de primer día. Downgrade se bloquea si ya hay configuraciones, para no perder trazabilidad.

Procedimiento para instalaciones todavía en la revisión anterior, siempre con autorización: verificar revisión real b1283aedf459 y ausencia de columnas incompatibles, conservar backup consistente, ejecutar exclusivamente upgrade c2394bfe056a contra el destino explícito y verificar integridad; después instalar el candidato y recargar únicamente los componentes necesarios. No desplegar el modelo antes del esquema: el sincronizador ordinario también importa Booking. Reversión del esquema solo antes de configurar inicios; una vez utilizado, conservar columnas y datos y revertir código compatible según revisión explícita.
La futura unión con la rama fiscal requiere un checkpoint separado, comprobación estructural y migración de unión tras aplicar legítimamente ambas ramas. No se resuelve ni activa facturación fiscal en este bloque.

## Validación
Pruebas de reservas antiguas, mes de entrada, prorrateos, fianza, borradores, histórico, liquidaciones cerradas, concurrencia, doble envío, revisión desactualizada, finalización anticipada y migración independiente. Regresión de finanzas, plan completo, finalización anticipada, liquidaciones y reutilización de personas.
Navegador real en 375/768/1280: HTTP 200, revisión y confirmación disponibles, sin desbordamiento horizontal ni errores JavaScript. Validación visual y funcional aprobada.

## Ejemplo aislado
Ejemplo de reserva antigua: contrato 01/09/2026–30/06/2027 (salida exclusiva), renta sintética 400 EUR, fianza 400 EUR. Inicio propuesto 01/12/2026: septiembre–noviembre excluidos; diciembre–mayo 6 × 400 EUR; junio 29/30 × 400 = 386,67 EUR; total 2.786,67 EUR. La fianza anterior no se genera como deuda. Guardar el inicio no crea cargos. Los datos económicos del ejemplo solo existen en la copia privada.

Validación previa al despliegue: 122 passed en batería Python consolidada; 1 passed de migración; 12 passed JavaScript. Aviso de deprecación existente de Starlette/httpx. Sobre una segunda copia de producción se confirmó diciembre y se generó el plan dos veces: 7 cargos contabilizados de renta por 2.786,67 EUR, cero pagos, cero fianzas automáticas y sin duplicados. La demostración se realizó sin modificar datos económicos productivos. quick_check ok y foreign_key_check limpio en producción (solo lectura), copia migrada, copia de demostración y copia de ejercicio.

El despliegue verificó hashes de los nueve componentes instalados, huellas de negocio sin cambios, ausencia de backfill y HTTP 200 en administración. Solo se reinició administración; web pública e iCal permanecieron intactos. Un primer intento se detuvo antes de migrar por la captura de stderr en Windows PowerShell; el reintento finalizó sin necesidad de reversión.

Cierre del checkpoint: 107 pruebas Python y 7 JavaScript correctas sobre HEAD más exclusivamente los doce archivos del bloque, sin depender de la reutilización de personas pendiente. git diff --check correcto. Los nueve componentes desplegados coinciden con los hashes del candidato aprobado. No se ejecutaron migraciones ni reinicios durante el cierre; se conserva la prueba de migración satisfactoria previa.
