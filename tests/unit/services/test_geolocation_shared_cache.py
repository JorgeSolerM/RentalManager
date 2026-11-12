import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from backend.public.map_locations import Address, LocationCache


def test_wal_reader_while_writer_holds_transaction(tmp_path):
    path = tmp_path / "shared.sqlite3"
    writer_cache = LocationCache(path)
    reader_cache = LocationCache(path)
    writer_cache.initialize()
    key = Address("Ejemplo", "1", "Elche").key
    with sqlite3.connect(path) as writer:
        writer.execute("INSERT INTO locations VALUES (?,?,?,?,?,?,?,?)",
                       (key,"review",None,None,"ambiguous",100,1,0))
        writer.commit()
        assert writer.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        writer.execute("BEGIN IMMEDIATE")
        writer.execute("UPDATE locations SET status='verified',latitude=38,longitude=-0.7 WHERE address_key=?", (key,))
        with ThreadPoolExecutor(max_workers=1) as pool:
            snapshot = pool.submit(reader_cache.read_many, {key}).result(timeout=5)
        assert snapshot[key]["status"] == "review"  # No partial/uncommitted read.
        writer.commit()
        assert reader_cache.read_many({key})[key]["status"] == "verified"


def test_read_only_connection_cannot_change_cache(tmp_path):
    cache = LocationCache(tmp_path / "shared.sqlite3")
    cache.initialize()
    with sqlite3.connect(cache.path.as_uri()+"?mode=ro",uri=True) as reader:
        with pytest.raises(sqlite3.OperationalError,match="readonly"):
            reader.execute("DELETE FROM locations")
