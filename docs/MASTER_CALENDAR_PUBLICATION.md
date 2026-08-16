# Publicación externa del calendario maestro

## Configuración operativa

La publicación externa de los calendarios maestros utiliza esta configuración:

- Dominio: `hsi-rents.com`.
- Endpoint público dedicado: `https://calendarios.hsi-rents.com`.
- Cloudflare Tunnel: `rentalmanager-calendars`.
- RentalManager/Uvicorn escucha únicamente en `127.0.0.1:8000`.
- El túnel publica exclusivamente las rutas que coinciden con `^/ical/.*`.
- `/` y cualquier otra ruta de RentalManager no se publican y devuelven `404`
  desde el hostname dedicado.
- La variable de entorno es
  `PUBLIC_BASE_URL=https://calendarios.hsi-rents.com`.
- No es necesario abrir el puerto `8000` en el router.
- La configuración existente de RDP permanece sin cambios.

Esta separación permite que las plataformas consulten los ficheros iCal sin
publicar la interfaz administrativa de RentalManager. La configuración no debe
contener tokens de Cloudflare, tokens de calendarios, credenciales ni URLs
completas de habitaciones.

## Validación externa realizada

Se ha comprobado desde una red externa que:

- una URL `.ics` válida es accesible mediante HTTPS;
- la vista de HousingAnywhere excluye sus propias reservas;
- la vista de Flatio incluye las reservas procedentes de HousingAnywhere;
- el feed no expone datos del huésped;
- `https://calendarios.hsi-rents.com/` devuelve `404` y no expone la interfaz
  administrativa.

## Revocación

La revocación genera tokens nuevos y hace que todas las URLs anteriores de la
Room dejen de funcionar inmediatamente. Después hay que sustituirlas en todas
las plataformas donde estén configuradas.

Los cambios ordinarios en las reservas no requieren revocar ni sustituir URLs:
el contenido publicado se actualiza conservando las direcciones existentes.
