from contextlib import contextmanager
from pathlib import Path

import portalocker

from backend.database.session import BASE_DIR


DEFAULT_LOCK_DIRECTORY = BASE_DIR / "data" / "runtime" / "locks"


class FileLockManager:
    def __init__(self, directory: Path | None = None):
        self.directory = directory or DEFAULT_LOCK_DIRECTORY

    @contextmanager
    def acquire(self, name: str):
        self.directory.mkdir(parents=True, exist_ok=True)
        lock = portalocker.Lock(
            self.directory / f"{name}.lock",
            mode="a",
            timeout=0,
            flags=portalocker.LOCK_EX | portalocker.LOCK_NB,
        )
        try:
            lock.acquire()
        except portalocker.exceptions.LockException:
            yield False
            return
        try:
            yield True
        finally:
            lock.release()
