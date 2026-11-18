# Activación de geolocalización e incidencias

## Reintento administrativo: activación realizada

La pantalla de revisión y las variantes se desplegaron con autorización el
18/11/2026. Administración dispone de escritura en la caché privada y el flag
`PUBLIC_GEOCODING_ADMIN_RETRY_ENABLED` está habilitado en su adaptador privado;
el valor por defecto del código continúa deshabilitado. Se validó un reintento
servido desde caché sin consultas al proveedor ni cambios de negocio.
Solo se reinició administración; la entrega pública y el calendario permanecieron
intactos. Se conservaron snapshot consistente, ACL y adaptador de reversión.
El acceso adicional desde el editor de fincas requiere un despliegue posterior.

Para repetir la activación en otro entorno, hace falta autorización para desplegar y dar al proceso
administrativo capacidad de escritura **solo en el directorio privado de caché y
SQLite/WAL/SHM**, conservando los demás límites, o implementar posteriormente un
escritor separado autorizado. No se promete separación NTFS entre una ruta de lectura
y otra de escritura dentro de la misma identidad Windows. No se cambia ahora ninguna
ACL. Ante falta de permisos el reintento muestra un aviso y no solicita elevación.

Procedimiento futuro: backup consistente de caché y arranques/ACL, validar en copia
la creación aditiva de `geocoding_queries` y `geocoding_attempts`, instalar candidato,
configurar User-Agent y flag administrativo, reiniciar únicamente servicios autorizados
y comprobar lectura pública/reintento/pausa. El worker periódico seguirá a cero.
El lector antiguo ignora las tablas adicionales; rollback de código no requiere
borrarlas ni restaurar coordenadas anteriores ni eliminar el historial.

Para aliases documentados, `PUBLIC_GEOCODING_ALIASES` apunta a un archivo privado
revisado, compartido por los escritores. Nunca habilitar Gerona/Girona únicamente
porque los nombres son traducciones: verificar que sea la misma calle y número.

Ambas aplicaciones comparten una única caché SQLite privada. No se requiere
migración de negocio. Las rutas, cuentas, acciones de tareas, ACL y copias de
seguridad concretas pertenecen al runtime local y no deben versionarse.

## Configuración

Cargar antes de importar backend, desde un mismo archivo privado, los valores
PUBLIC_GEOCODING_CACHE (ruta absoluta existente) y PUBLIC_GEOCODER_URL.
Forzar PUBLIC_GEOCODING_WORKER_ENABLED=0 en ambos adaptadores; activar
PUBLIC_MAP_ENABLED=1 únicamente en el público. No duplicar cachés por servicio.

## Permisos y concurrencia

Identificar cuentas reales antes de intervenir; reutilizar el arranque existente.
La cuenta administrativa lee SQLite/WAL/SHM y atraviesa la carpeta; el escritor
necesita modificar caché y carpeta. SYSTEM y administradores conservan control.
Retirar accesos heredados innecesarios, preservando aparte permisos de logs.
Si los servicios comparten cuenta, NTFS no puede distinguir sus roles: resolver
esa configuración antes de prometer separación de permisos.

El lector utiliza mode=ro; no usar immutable=1 en una caché mutable. Inicializar
WAL/SHM antes de habilitar lectores restringidos. Verificar bajo las identidades
reales después del reinicio. Tests comprueban lectura durante una transacción,
ausencia de datos parciales, visibilidad tras commit y rechazo de escrituras.

## Activación y reversión

1. Preparar release público aislado y adaptadores inactivos; contrastar hashes.
2. Guardar arranques, tareas y SDDL/propietarios; snapshot consistente SQLite
   exclusivamente para reversión, nunca como segunda caché operativa.
3. Obtener autorización para instalación, ACL y reinicios de servicios afectados.
4. Instalar y reiniciar de uno en uno; no tocar iCal, Cloudflare ni datos de negocio.
5. Verificar HTTP local/HTTPS, mapa, incidencias, colaboradores, rutas privadas 404,
   permisos, integridad y comparación lógica de tablas.

Ante fallo crítico, restaurar arranques/release/ACL y reiniciar solo los servicios
afectados. Conservar caché/cooldown. No borrar WAL ni restaurar un snapshot salvo
corrupción demostrada y con los usuarios SQLite detenidos. El rollback normal
no modifica la BD de negocio.

## Validación del checkpoint

Activación controlada realizada: ambos servicios HTTP 200, catálogo HTTPS con
cuatro marcadores y cuatro incidencias administrativas. Sin cambios lógicos en
caché ni negocio, worker apagado. Validación visual previa aprobada por el usuario;
la comprobación visual posterior se interrumpió por una limitación del controlador
para identificar la URL del navegador.

Después del reinicio se comprobó una URL iCal maestra existente: HTTPS 200,
text/calendar, VCALENDAR 2.0 y eventos válidos. Se eligió una vista exportable sin
registro de observación asociado para no actualizar contadores. La comparación
lógica de la BD antes/después no mostró cambios. No se versionan URL ni ICS.

Los adaptadores productivos, resultados detallados y backups quedan fuera de Git.
