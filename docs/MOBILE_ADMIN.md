# Administración móvil y presentación remota

La adaptación conserva las operaciones del escritorio local y utiliza
`request.state.admin_remote` para renderizar la presentación de consulta remota.
No sustituye las barreras de seguridad del servidor ni amplía sus permisos.

## Componentes

- `layouts/base.html`, `components/header.html` y `components/sidebar.html`:
  cabecera compacta, indicador «Modo consulta» y menú Bootstrap Offcanvas.
- `admin_mobile.css` y `admin_mobile.js`: adaptación hasta 768 px y en teléfonos
  horizontales con puntero táctil hasta 1024 × 500 px; tablas con scroll interno,
  controles táctiles, formularios y modales. No se añaden dependencias externas.
- `gantt.css`, `gantt.js` y `pages/gantt.html`: columna móvil de habitaciones de
  116 px, fechas fijas, desplazamiento nativo, filtros plegables, zoom visual
  1×/2×/4× independiente del intervalo 4/8/12 meses y modo ampliado con salida
  visible. Al rotar se conserva el centro temporal y el desplazamiento vertical,
  limitados por los extremos del contenido. Las barras mantienen su intervalo
  real; la lista por habitación permite seleccionar reservas muy cortas.
- `booking_reader.html` y `booking_reader.js`: lectura de reserva y contactos
  desde endpoints previamente autorizados. Los enlaces tel, mailto y WhatsApp
  solo abren aplicaciones al pulsarlos. WhatsApp exige prefijo internacional;
  no se infiere el país ni se envían mensajes automáticamente.
- Plantillas administrativas y económicas: no renderizan operaciones mutadoras
  ni navegación restringida en consulta remota; conservan consultas y búsquedas.

## Seguridad

No se modifican JWT, CSRF, MFA, la lista de rutas autorizadas ni la conexión de
base de datos de solo lectura. El estado remoto procede del servidor, no de un
parámetro del navegador. La ausencia de botones no constituye autorización.
Los contactos se cargan bajo demanda, mediante las fichas ya autorizadas.

## Validación

Se comprueban 360, 375, 390, 430, 768, 1280 y 1920 px, orientación horizontal,
menú, zoom, filtros, ampliación, posición, selección y contactos. Las pruebas
de creación/edición y reutilización de personas usan únicamente bases sintéticas.
`tests/integration/test_mobile_remote_presentation.py` verifica la presentación,
la búsqueda GET de personas, el editor local y el rechazo de escritura remota.
La búsqueda POST del desarrollo pendiente de reutilización se prueba por separado
en el candidato combinado; ese desarrollo no forma parte de este commit.

Las baterías de CSRF y seguridad remota se mantienen. Los cuatro fallos previos
del candidato combinado (tres expectativas de Cache-Control de reutilización y
una de número de consultas de habitaciones) no se modifican para ocultarlos.
La emulación táctil no sustituye una comprobación posterior en Android físico.

## Despliegue y reversión

1. Verificar el manifiesto aprobado: hash de origen y hash del candidato por
   archivo. Detenerse ante cambios posteriores. Revisar el diff para excluir
   desarrollos pendientes, datos, credenciales y artefactos privados.
2. Respaldar los archivos existentes y sus permisos; registrar los nuevos como
   ausentes. Conservar un script de reversión que compruebe hashes antes de actuar.
3. Copiar exclusivamente los recursos y plantillas aprobados, recursos primero
   y referencias después, mediante reemplazos por archivo. No copiar bases,
   servidores de prueba, configuración privada ni directorios de ejecución.
4. Verificar hashes y páginas nuevas. Jinja usa recarga automática; no se necesita
   reinicio para esta entrega. Las pestañas abiertas deben recargarse.
5. Comprobar integridad de SQLite en modo de solo lectura, disponibilidad local,
   rechazos de identidad inválida y pruebas aisladas de escritura. No insertar
   reservas ni movimientos de prueba en producción.
6. Para revertir: comprobar que los archivos activos aún corresponden al
   despliegue, restaurar los respaldos y retirar únicamente los recursos nuevos
   enumerados. No revertir CSRF ni modificar autenticación, datos o Cloudflare.

El respaldo, manifiesto de bytes, registros y script de reversión se conservan
fuera de Git, en el directorio privado de ejecución del despliegue. Los cambios
locales ajenos permanecen sin incluirse en el commit. Web pública, iCal,
sincronizaciones y subfases económicas quedan fuera de esta entrega.
