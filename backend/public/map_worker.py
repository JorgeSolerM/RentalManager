"""Optional background geocoding; never part of an HTTP request transaction."""
from contextlib import asynccontextmanager
import logging
import os
from threading import Event, Thread

from backend.public.database import PublicSessionLocal
from backend.public.map_locations import map_enabled, refresh_locations


def run(stop):
    while not stop.is_set():
        try:
            with PublicSessionLocal() as db:
                refresh_locations(db, stop=stop)
        except Exception:
            # Do not log addresses, URLs, or exception payloads from providers.
            logging.getLogger(__name__).warning("Geocoding worker failed; retry deferred")
        stop.wait(300)


@asynccontextmanager
async def lifespan(app):
    stop = Event()
    worker = None
    if map_enabled() and os.getenv("PUBLIC_GEOCODING_WORKER_ENABLED", "0") == "1":
        worker = Thread(target=run, args=(stop,), daemon=True, name="public-geocoding")
        worker.start()
    try:
        yield
    finally:
        stop.set()


if __name__ == "__main__":
    with PublicSessionLocal() as session:
        print(refresh_locations(session))
