"""Read-only projection into the existing, derived Dashboard incidents."""
from datetime import datetime, timezone
import os
from zoneinfo import ZoneInfo

from sqlalchemy import select

from backend.models.property import Property
from backend.public.map_locations import Address, LocationCache
from backend.schemas.dashboard_schema import DashboardIncident


REASONS = {
    "ambiguous": "Se encontraron varias ubicaciones posibles.",
    "no_exact_street_number_city": "No se pudo verificar conjuntamente calle, número y ciudad.",
    "incomplete_address": "Faltan calle, número o ciudad en la dirección registrada.",
    "provider_unavailable": "El proveedor no respondió correctamente; no se conservó el detalle técnico del primer fallo.",
    "timeout": "El proveedor agotó el tiempo de respuesta.",
    "connection_error": "No se pudo conectar con el proveedor.",
    "invalid_response": "El proveedor devolvió una respuesta no válida.",
    "interrupted": "El intento anterior no llegó a completarse.",
}


def geolocation_incidents(db, cache=None):
    cache = cache or LocationCache()
    # No alerts for installations where the map has never been configured.
    if not cache.path.exists() and not os.getenv("PUBLIC_GEOCODING_CACHE"):
        return []
    properties = db.scalars(select(Property).where(
        Property.active.is_(True), Property.is_published.is_(True)
    ).order_by(Property.id)).all()
    entries = cache.read_many({Address.of(p).key for p in properties})
    incidents = []
    for prop in properties:
        address = Address.of(prop)
        entry = entries.get(address.key)
        if entry and entry["status"] == "verified":
            continue
        status = entry["status"] if entry else "pending"
        label = {"error": "Error del proveedor", "review": "Requiere revisión"}.get(status, "Pendiente")
        reason = entry["reason"] if entry else "not_attempted"
        explanation = REASONS.get(reason, "Ubicación pendiente de verificar; puede estar aplazada por la pausa del proveedor.")
        if reason.startswith("http_") and reason[5:].isdigit():
            explanation = f"El proveedor respondió con HTTP {reason[5:]}."
        attempted = "Sin intento para la dirección actual"
        if entry and entry.get("checked_at") and entry.get("attempts", 0):
            when = datetime.fromtimestamp(entry["checked_at"], timezone.utc).astimezone(ZoneInfo("Europe/Madrid"))
            attempted = f"Último intento: {when:%d/%m/%Y %H:%M} (Europe/Madrid)"
        registered = ", ".join(filter(None, (f"{address.street} {address.number}".strip(), address.city))) or "Dirección sin informar"
        incidents.append(DashboardIncident(
            key=f"geolocation:{prop.id}", kind="geolocation", severity="attention",
            title=f"Geolocalización · {label}",
            detail=f"{prop.name} · {registered} · {explanation} · {attempted}",
            target_url=f"/properties/{prop.id}",
        ))
    return incidents
