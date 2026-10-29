# Calendario de colaboradores

Implementado en la aplicación pública separada. Validación funcional y visual
aprobada el 29/10/2026; despliegue pendiente de autorización independiente.
No modifica reservas, facturación, liquidaciones ni sincronización.
No necesita tablas ni migraciones. Deshabilitado sin configuración de acceso.

## Selección aprobada

- Ventana diaria `[hoy, hoy + seis meses naturales)`, fecha de negocio Madrid.
- Se reutiliza el cargador público: todas las reservas con salida posterior a hoy,
  **sin límite superior**. No se utiliza la consulta acotada del Gantt administrativo.
- `available_from = max(hoy, salidas efectivas de todas esas reservas)`.
- Solo aparece una habitación si esa fecha está dentro de la ventana.
- Se respetan publicación efectiva, Room activa/puesta en servicio y requisitos de
  finca/gestor del catálogo. No basta con is_published.
- Una habitación libre hoy con reserva futura no se ofrece desde hoy: solo desde
  la última salida conocida, si cae dentro de la ventana.
- Reservas posteriores a la ventana también excluyen habitaciones. No se ofrecen
  huecos intermedios; se dibujan neutros y se identifican como no ofrecidos.
- Ocupación `[check_in, check_out)`, como Gantt. El día de salida está libre.
  Una finalización anticipada confirmada actualiza check_out; no se sustituye por
  la fecha económica ni por una mera previsión de salida.
- Los bloqueos representados como Booking usan el mismo criterio que Gantt. No
  se inventan estados ni un segundo calendario de ocupación.

La definición comercial existente de huecos del catálogo no se cambia. El helper
terminal está separado y probado para impedir regresiones entre ambos criterios.

## Interfaz y privacidad

Solo nombres públicos, fechas de ocupación y enlaces oficiales de anuncios.
No se serializan IDs de reservas, personas, teléfonos, notas ni datos económicos.
El nombre de finca en **cada fila** abre el anuncio de esa habitación; aprobado
expresamente porque no existe ficha pública de finca. Texto accesible: «Ver anuncio
de esta habitación». No se inventan rutas de finca.

Tabla diaria agrupada por finca, etiquetas fijas, desplazamiento interno por
teclado/táctil, símbolos y texto además del color. No acciones de reserva/edición.
Lectura con conexión SQLite mode=ro. Actualización cada 60 segundos. Si falla la
actualización o se revoca acceso, se retiran los datos previos de la vista.

## Acceso revocable (despliegue futuro, no aplicado en producción)

Ruta: `/colaboradores/disponibilidad#<secreto>`.
Generar privadamente 32 bytes aleatorios mediante `secrets.token_urlsafe(32)`.
Guardar únicamente su SHA-256 hexadecimal en configuración del proceso público:

- `COLLABORATOR_CALENDAR_TOKEN_HASH_FILE`: archivo privado con el digest, leído en
  cada petición. Preferido: permite revocar/rotar sin reiniciar.
- Alternativa: `COLLABORATOR_CALENDAR_TOKEN_SHA256` en entorno del proceso.

No versionar secreto, archivo privado ni enlace completo. El fragmento no viaja
al servidor como URL: JavaScript lo envía en Authorization al endpoint `/data`.
No usar query parameters. La página inicial es una carcasa sin datos; `/data`
exige Bearer válido. Falta de configuración devuelve 404, acceso inválido 401.
No hay cookies, localStorage, sessionStorage ni analítica. No logs de Authorization;
el despliegue/proxy tampoco debe habilitarlos. HTTPS obligatorio al publicar.
Cabeceras no-store, no-referrer y noindex/nofollow/noarchive; no sitemap ni menús.
Los enlaces al anuncio no transmiten el secreto ni Referer.

Revocar: sustituir el digest por el de un secreto nuevo (o retirar configuración).
Las nuevas consultas fallan inmediatamente; una vista abierta se vacía en su
siguiente refresco, normalmente antes de un minuto. No se pueden retirar capturas
ya tomadas. Cualquiera con el enlace puede consultarlo: es acceso compartido, no
identidad individual ni autorización para reservar. No distribuir públicamente.

## Validación

Fixtures exclusivamente sintéticos. Integración: siete ejemplos aprobados, límites
de seis meses, reservas lejanas, publicación, finalizaciones anticipadas, iCal,
solapamientos, consultas acotadas, DTO mínimo, revocación y ausencia de mutaciones.
JavaScript: transporte autorizado, ausencia de token en DOM/enlaces, huecos neutros,
salida exclusiva, refresco/revocación y acceso desde fragmento sin recargar.
Entorno temporal privado en data/runtime, excluido de Git; no usa la BD real.

Resultados de validación del checkpoint (29/10/2026):

- 103 tests Python: integración pública, disponibilidad, Gantt y finalización
  anticipada.
- 64 tests Python adicionales: sincronización iCal, facturación y liquidaciones.
- 4 tests JavaScript del calendario.
- Navegador: 375/768/1280 px, sin overflow del documento, desplazamiento interno
  con teclado, anuncios abiertos correctamente y consola sin errores.
- Integridad SQLite: quick_check correcto y foreign_key_check vacío; consulta
  productiva exclusivamente en lectura. Ninguna migración de este checkpoint.

## Procedimiento futuro de publicación

1. Obtener autorización expresa para desplegar. Revisar el conjunto de commits:
   este checkpoint tiene como antecesor el commit local de preparación fiscal;
   no desplegar/activar ese módulo incidentalmente ni aplicar su migración.
   El calendario no añade dependencia funcional de facturación ni librerías.
2. Preparar una entrega revisada con las rutas del calendario, el helper de
   disponibilidad y el registro en la aplicación pública. Verificar compatibilidad
   con la versión desplegada y ejecutar sus tests antes de cambiar el proceso.
3. Generar un secreto NUEVO de producción (no reutilizar el sintético). Guardar
   privadamente el enlace y el digest en un archivo accesible solo por la cuenta
   del proceso público y administradores. Configurar
   COLLABORATOR_CALENDAR_TOKEN_HASH_FILE en el arranque público persistente.
4. Con autorización de despliegue, recargar únicamente el proceso público que
   escucha en 127.0.0.1:8001. No modificar administración, sincronizador, DNS ni
   túnel de calendarios. No se necesita nueva ruta de Cloudflare si el hostname
   público ya dirige todos sus paths a este proceso.
5. Verificar en HTTPS la carcasa sin datos, /data sin token (401), token correcto
   (200), token incorrecto (401), no-store/noindex/no-referrer, anuncios sin token,
   rechazo de POST y ausencia en sitemap/menús. Comprobar también portada/fichas.
6. Distribuir privadamente el enlace con fragmento a colaboradores autorizados.
   Nunca copiarlo a documentación, logs o repositorio. Verificar que ningún proxy
   registra Authorization ni cachea las respuestas.
7. Revocación: reemplazar atómicamente el archivo de digest con el hash de otro
   secreto privado, o retirar el archivo para deshabilitar. No requiere reinicio.
   Probar que el enlace anterior ya no obtiene datos y distribuir el nuevo solo
   si procede. Para rollback del acceso basta retirar ese archivo; no hay datos
   ni migración que deshacer.

Estos pasos están documentados, no ejecutados en producción durante el cierre.
