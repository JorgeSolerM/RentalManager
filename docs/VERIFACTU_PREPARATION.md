# Preparación VERI*FACTU: límites y verificación técnica

Implementación detallada y escenarios: [FEE_INVOICING_IMPLEMENTATION.md](FEE_INVOICING_IMPLEMENTATION.md).

## Implementado, exclusivamente sintético

- Alta ordinaria completa F1. XML puro local, sin SOAP/HTTP ni certificados.
- `InvoiceFiscalRecord`: snapshot, timestamp con huso, huella y anterior inmutables.
- Cadena por obligado + SIF/instalación + entorno, no serie/propietario/finca.
- Hash SHA-256 en mayúsculas; orden y valores oficiales, con bruto y cuota de IVA
  congelados. Dos vectores públicos de AEAT cubren primer registro y sucesivo.
- QR oficial **de pruebas**, numserie codificado, fecha DD-MM-AAAA e importe bruto.
  PDF de prueba con aviso inequívoco; no evidencia de remisión.
- Alta de la cola test en la misma transacción de emisión; gestión posterior de
  intentos en transacciones separadas. Mocks guardan
  resultado e intento; no producen otra factura ni alteran el registro fiscal.
- Serializador agrega únicamente desgloses fiscalmente idénticos sumando cuotas
  exactas, sin recalcular IVA. Líneas de factura/finca/fuente permanecen separadas.
- XML F1 contrastado localmente con SuministroLR/SuministroInformacion de AEAT y
  esquema XMLDSig de W3C. Resolver local sin red durante validación. Los XSD y
  artefactos de auditoría se mantienen en runtime ignorado, no como dependencias
  remotas de ejecución de la aplicación.

Referencias: [AEAT hash](https://www.agenciatributaria.es/static_files/AEAT_Desarrolladores/EEDD/IVA/VERI-FACTU/Veri-Factu_especificaciones_huella_hash_registros.pdf),
[AEAT QR](https://www.agenciatributaria.es/static_files/AEAT_Desarrolladores/EEDD/IVA/VERI-FACTU/DetalleEspecificacTecnCodigoQRfactura.pdf),
[XSD AEAT](https://prewww2.aeat.es/static_files/common/internet/dep/aplicaciones/es/aeat/tikeV1.0/cont/ws/SuministroLR.xsd).

## Probado sintéticamente / validación funcional y visual aprobada

Entorno recuperado el 29/10/2026 en `http://127.0.0.1:8119`. BD nueva migrada por
`fe0618cad237 -> b1283aedf459 -> a01729dbe348`, separada de producción. Casos A-I
preparados y posteriormente aprobados por el usuario, junto con configuración y
PDF. Los diálogos de cierre/emisión del flujo manual no fueron automatizados.
Los tests locales cubren hash, encadenamiento, cuotas, XML, numeración, rollback,
idempotencia e inmutabilidad. La validación XSD offline no es una remisión AEAT.
En esta recuperación se han generado cinco XML nuevos desde los registros
sintéticos actuales: los cinco pasan los XSD locales. Cinco PDF de prueba
renderizados/revisados y cero intentos de remisión. No se ha instalado ninguna
dependencia nueva ni descargado esquemas durante esta comprobación.
Batería consolidada del 29/10/2026: 663 tests Python correctos (un aviso de
deprecación TestClient/httpx), más 7 tests JavaScript de regresión de finalización
anticipada. No se suman ejecuciones enfocadas que solapan esta batería.

## Deshabilitado en producción

Producción mantiene `b1283aedf459`; las tablas fiscales preexistentes se reconocerán
solo mediante upgrade autorizado y comprobación estructural exacta, nunca stamp.
El ensayo sobre copia consistente conserva estructuras y datos. No se han
consumido números productivos ni habilitado flags de emisión real.

## Pendiente de integración AEAT: no confundir con cumplimiento productivo

XSD, hash y tests locales no acreditan aceptación censal, criterio fiscal correcto,
aceptación AEAT, cumplimiento integral del SIF ni declaración responsable. Antes
de producción: validación fiscal humana y AEAT, transporte/certificados seguros,
worker de remisión, gestión real de respuestas/reintentos, rectificativas,
subsanaciones, anulaciones y
declaración del productor sobre el conjunto efectivamente validado.

Emisión real y `VERIFACTU_SUBMISSION_ENABLED` siguen bloqueados. No se ha enviado
ningún registro ni utilizado certificados reales en este checkpoint.
