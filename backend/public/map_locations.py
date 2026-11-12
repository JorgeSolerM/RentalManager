"""Verified geocoding cache, separate from the read-only business database.

Only the server worker/CLI writes here; a catalog request never geocodes.
"""
from dataclasses import dataclass
from hashlib import sha256
import json
import logging
import math
import os
from pathlib import Path
import re
import sqlite3
import time
import unicodedata
from urllib.parse import urlsplit

import httpx
from sqlalchemy import select

from backend.models.property import Property
from backend.models.room import Room

log = logging.getLogger(__name__)


def map_enabled():
    return os.getenv("PUBLIC_MAP_ENABLED", "0") == "1"


def cache_path():
    return Path(os.getenv("PUBLIC_GEOCODING_CACHE", "data/runtime/geocoding/locations.sqlite3")).resolve()


def tile_url():
    value = os.getenv("PUBLIC_MAP_TILE_URL", "https://tile.openstreetmap.org/{z}/{x}/{y}.png")
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or not re.fullmatch(r"[A-Za-z0-9.-]+(?::[0-9]+)?", parsed.netloc)):
        raise ValueError("Map tiles require an HTTPS public URL")
    return value


def normalize(value):
    return " ".join(re.sub(r"[^a-z0-9]+", " ", "".join(
        c for c in unicodedata.normalize("NFKD", value or "").lower()
        if not unicodedata.combining(c)
    )).split())


def street_key(value):
    # Only equivalent road-type prefixes, never fuzzy proper-name matching.
    return re.sub(r"^(calle|carrer|c|avenida|avinguda|av|plaza|placa|pl) ", "", normalize(value))


def city_key(value):
    key = normalize(value)
    return "elche" if key in {"elche", "elx", "elche elx", "elx elche"} else key


@dataclass(frozen=True)
class Address:
    street: str
    number: str
    city: str

    @classmethod
    def of(cls, property_obj):
        return cls(*(str(getattr(property_obj, field) or "").strip()
                     for field in ("street", "street_number", "city")))

    @property
    def key(self):
        # Provider and validation version prevent reuse after changing policy.
        parts = ["strict-v1", geocoder_url(), *(normalize(x) for x in (self.street, self.number, self.city))]
        return sha256(json.dumps(parts).encode()).hexdigest()


def geocoder_url():
    return os.getenv("PUBLIC_GEOCODER_URL", "https://nominatim.openstreetmap.org/search")


def verified_result(address, results):
    matches = set()
    for item in results if isinstance(results, list) else []:
        if not isinstance(item, dict):
            continue
        detail = item.get("address") or {}
        if not isinstance(detail, dict):
            continue
        city = detail.get("city") or detail.get("town") or detail.get("village") or ""
        if (city_key(city) != city_key(address.city)
                or street_key(detail.get("road", "")) != street_key(address.street)
                or normalize(detail.get("house_number", "")) != normalize(address.number)):
            continue
        try:
            lat, lon = float(item["lat"]), float(item["lon"])
        except (KeyError, ValueError, TypeError):
            continue
        if math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180:
            matches.add((lat, lon))
    if len(matches) == 1:
        return "verified", next(iter(matches)), "exact_street_number_city"
    return "review", None, "ambiguous" if matches else "no_exact_street_number_city"


class LocationCache:
    def __init__(self, path=None):
        self.path = Path(path).resolve() if path else cache_path()

    def initialize(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("CREATE TABLE IF NOT EXISTS locations (address_key TEXT PRIMARY KEY, status TEXT NOT NULL, latitude REAL, longitude REAL, reason TEXT NOT NULL, checked_at REAL NOT NULL, attempts INTEGER NOT NULL, retry_at REAL NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS throttle (id INTEGER PRIMARY KEY CHECK(id=1), next_request REAL NOT NULL)")
            db.execute("INSERT OR IGNORE INTO throttle VALUES (1,0)")

    def read_many(self, keys):
        if not self.path.exists() or not keys:
            return {}
        try:
            with sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=1) as db:
                db.row_factory = sqlite3.Row
                rows = db.execute("SELECT * FROM locations WHERE address_key IN (" + ",".join("?" for _ in keys) + ")", list(keys))
                return {row["address_key"]: dict(row) for row in rows}
        except sqlite3.Error:
            log.warning("Geocoding cache unavailable; map locations omitted")
            return {}

    def resolve(self, address, *, client, clock=time.time, sleep=time.sleep):
        """Serialize requests across workers; WAL catalog readers remain unblocked."""
        key = address.key
        with sqlite3.connect(self.path, timeout=40) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT status,attempts,retry_at FROM locations WHERE address_key=?", (key,)).fetchone()
            now = clock()
            if row and (row[0] != "error" or row[1] >= 3 or row[2] > now):
                return row[0]
            if not all((address.street, address.number, address.city)):
                db.execute("INSERT OR REPLACE INTO locations VALUES (?,?,?,?,?,?,?,?)", (key,"review",None,None,"incomplete_address",now,0,0))
                return "review"
            next_request = db.execute("SELECT next_request FROM throttle WHERE id=1").fetchone()[0]
            if next_request - now > 16.1:
                return "error"  # Provider cooldown, never sleep for a whole day.
            if next_request > now:
                sleep(next_request - now)
            attempts = row[1] + 1 if row else 1
            db.execute("UPDATE throttle SET next_request=? WHERE id=1", (clock()+16,))
            db.execute("INSERT OR REPLACE INTO locations VALUES (?,?,?,?,?,?,?,?)", (key,"error",None,None,"interrupted",clock(),attempts,clock()+86400))
            try:
                response = client.get(geocoder_url(), params={
                    "street": f"{address.number} {address.street}", "city": address.city,
                    "format": "jsonv2", "addressdetails": 1, "limit": 10,
                    "accept-language": "es",
                })
                response.raise_for_status()
                status, point, reason = verified_result(address, response.json())
                db.execute("UPDATE throttle SET next_request=? WHERE id=1", (clock()+16,))
            except (httpx.HTTPError, ValueError) as error:
                reason = (f"http_{error.response.status_code}" if isinstance(error, httpx.HTTPStatusError)
                          else "timeout" if isinstance(error, httpx.TimeoutException)
                          else "connection_error" if isinstance(error, httpx.NetworkError)
                          else "invalid_response")
                status, point = "error", None
                # Provider-wide cooldown; never hammer 403/429/5xx or timeouts.
                db.execute("UPDATE throttle SET next_request=? WHERE id=1", (clock()+86400,))
            db.execute("UPDATE locations SET status=?,latitude=?,longitude=?,reason=?,checked_at=?,retry_at=? WHERE address_key=?", (
                status, point[0] if point else None, point[1] if point else None, reason,
                clock(), clock()+86400 if status == "error" else 0, key))
            return status


def refresh_locations(db, cache=None, client=None, stop=None):
    cache = cache or LocationCache()
    cache.initialize()
    properties = db.scalars(select(Property).where(Property.active.is_(True), Property.is_published.is_(True))).all()
    own_client = client is None
    if own_client:
        agent = os.getenv("PUBLIC_GEOCODER_USER_AGENT", "").strip()
        if not agent:
            raise ValueError("PUBLIC_GEOCODER_USER_AGENT must identify the application and contact")
        if urlsplit(geocoder_url()).scheme != "https":
            raise ValueError("Geocoder must use HTTPS")
        client = httpx.Client(headers={"User-Agent": agent}, timeout=15, follow_redirects=False)
    counts = {"verified": 0, "review": 0, "error": 0}
    try:
        for prop in properties:
            if stop and stop.is_set():
                break
            status = cache.resolve(Address.of(prop), client=client)
            counts[status] += 1
            if status != "verified":
                log.warning("Map location: property_id=%s status=%s (see private cache reason)", prop.id, status)
            if status == "error":
                with sqlite3.connect(cache.path) as connection:
                    cooldown = connection.execute("SELECT next_request FROM throttle WHERE id=1").fetchone()[0]
                if cooldown > time.time() + 16.1:
                    break
    finally:
        if own_client:
            client.close()
    return counts


def catalog_map(db, rooms):
    """Project the EXACT catalog selection, never run a second availability algorithm."""
    if not map_enabled():
        return None
    if not rooms:
        return {"properties": [], "omitted": 0, "tiles": tile_url()}
    rows = db.execute(select(Room.public_slug, Property.id, Property.public_title,
                             Property.street, Property.street_number, Property.city)
                      .join(Property, Property.id == Room.property_id)
                      .where(Room.public_slug.in_([r.slug for r in rooms]))).all()
    addresses = {r.public_slug: (r, Address(r.street or "", r.street_number or "", r.city or "")) for r in rows}
    cached = LocationCache().read_many({a.key for _, a in addresses.values()})
    groups = {}
    omitted = 0
    for card in rooms:
        if card.slug not in addresses:
            omitted += 1
            continue
        row, address = addresses[card.slug]
        entry = cached.get(address.key)
        if not entry or entry["status"] != "verified":
            omitted += 1
            continue
        group = groups.setdefault(row.id, {"name": row.public_title, "latitude": entry["latitude"], "longitude": entry["longitude"], "rooms": []})
        group["rooms"].append({"title": card.title, "slug": card.slug,
                               "price": str(card.price_monthly), "image": card.primary_image.url_320})
    return {"properties": list(groups.values()), "omitted": omitted, "tiles": tile_url()}
