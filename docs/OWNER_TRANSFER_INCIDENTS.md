# Incidencias de transferencias a propietarios — fase 2

## Estado
Implementado, probado en candidato aislado y desplegado mediante activación controlada. Producción está en 289fa146bc01. La validación posterior superó 211 pruebas sobre bases aisladas con los componentes instalados; las cuatro tablas nuevas permanecían vacías al cerrar el despliegue. No se realizan transferencias ni consultas bancarias. Fases 3 (recuperaciones) y 4 (regularizaciones excepcionales) pendientes. VERI*FACTU fuera del alcance.

## Separación económica
Una incidencia sobre OwnerPayout conserva su salida bancaria y el registro original. La parte no recibida válidamente deja de satisfacer la obligación con el propietario, pero no vuelve a los fondos disponibles. Si una cuenta incorrecta pertenece al mismo propietario y la recepción está acreditada, el pago sigue siendo válido.

Una salida extraordinaria representa exclusivamente dinero efectivamente transferido que no está representado por OwnerPayout. No satisface automáticamente ninguna liquidación del destinatario accidental. Reduce los fondos explícitamente atribuidos y puede generar un déficit visible. Los fondos disponibles se limitan a cero; el déficit se informa por separado.

El cálculo común distingue pagos vigentes, devoluciones reales previas, pago válido, pendiente, salidas extraordinarias, dinero pendiente de recuperar, fondos disponibles y déficit. Las devoluciones anteriores se descuentan una sola vez. Registrar una incidencia o atribuir sus fondos no crea entradas de dinero.

## Modelo y trazabilidad
- OwnerTransferIncident: origen, liquidación/propietario previstos, cadena canónica de payout, destinatario conocido/desconocido, importe afectado, motivo y evidencias.
- OwnerTransferOutflow: salida extraordinaria real, fecha, referencia e identidad bancaria; cuentas conservadas únicamente como huella y últimos cuatro caracteres.
- OwnerTransferIncidentOperation: registro y atribución posterior inmutables, operador disponible, fecha UTC, estados anterior/posterior, idempotencia y huella revisada.
- OwnerTransferIdentity: identidad bancaria lateral sin alterar OwnerPayout; evita registrar de nuevo una salida conocida.

El estado se deriva del historial. Los datos originales, las cadenas de sustitución, cierres, consumos y PDF históricos se conservan. Una nueva generación documental puede reflejar incidencias; no reemplaza versiones anteriores.

## Atribución y bloqueos
La salida debe atribuirse completamente a fondos identificados o quedar pendiente. Si se conoce el ámbito, se bloquean nuevos payouts de esos propietarios; sin ámbito fiable, el bloqueo es general. La atribución posterior exige preview, motivo y confirmación; libera el bloqueo solo al identificar íntegramente los fondos. No atribuye dinero al destinatario accidental.

Se bloquean correcciones administrativas y devoluciones ordinarias de cadenas con incidencia. Se conservan los bloqueos de compensaciones. Las operaciones se revalidan dentro de transacción de escritura SQLite; las huellas incluyen fondos compartidos y movimientos relevantes. No se admiten doble registro, doble atribución ni previews desactualizadas.

## Identidad bancaria y límites
Los identificadores bancarios fiables se contrastan con la cuenta de origen. Las coincidencias de importe/fecha/destino se tratan conservadoramente. Para registrar una segunda transferencia similar se exigen identificadores distintos y evidencia del original. Una referencia libre diferente no demuestra por sí sola otra salida.

Sin conexión bancaria no se puede demostrar automáticamente la veracidad del justificante: el operador debe confirmar la ejecución real. Las coincidencias ambiguas quedan bloqueadas. No se importan ni adjuntan documentos privados en esta fase; evidencia es una descripción administrativa, con IBAN redactado.

Se admite una incidencia por cadena de payout y una atribución definitiva posterior por salida. No se implementan redistribuciones posteriores, reclasificación de destinatario, recuperaciones parciales/totales ni condonaciones. Estas requieren el circuito posterior; no deben simularse con anulaciones o devoluciones ordinarias.

## Interfaz
Desde una liquidación cerrada: Registrar transferencia errónea / Registrar transferencia duplicada. El formulario distingue salida ya registrada de salida extraordinaria. La vista previa presenta pago válido, obligación pendiente, fondos afectados, pendiente de recuperar y déficit. Se exige motivo, evidencia y confirmación expresa de ejecución. El historial muestra operaciones enlazadas y cuentas enmascaradas. Rutas solo administrativas, respuestas privadas sin caché.

## Migración y procedimiento de despliegue
289fa146bc01 depende exclusivamente de 178e9035abf0. Crea cuatro tablas, índices y guardas adicionales. No modifica las guardas de inmutabilidad existentes de OwnerPayout. Probada mediante upgrade/downgrade/upgrade en copia consistente; conserva tablas anteriores y triggers existentes.

No usar stamp ni upgrade heads. Para reproducir el despliegue en otro entorno autorizado: copia consistente, comprobar revisión/esquema y manifiesto, aplicar solo esta revisión y validar administración. La reversión de esquema se bloquea si existen registros nuevos. Tampoco se debe restaurar código anterior ignorando incidencias ya registradas: podría permitir pagos sobre fondos comprometidos. En ese caso detener nuevas operaciones y preparar una reversión compatible con los datos.

## Validación
Pruebas unitarias, HTTP completos y migración cubren destinatarios, recepción acreditada, duplicados, déficit, atribución global/acotada, copropiedad, devoluciones previas, sustituciones, privacidad, concurrencia, rollback, idempotencia y PDF históricos. Regresión de devoluciones, correcciones administrativas, liquidaciones, documentos y gastos. Sin llamadas bancarias y sin escrituras productivas.

Los escenarios navegables sintéticos se facilitan en el informe del candidato; sus rutas y artefactos de ejecución no forman parte del código a versionar. Revisión responsive a 375/768/1280 px, sin desbordamiento horizontal ni errores JavaScript.
