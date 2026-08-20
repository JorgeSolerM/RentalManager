from dataclasses import dataclass
from pathlib import Path
import shutil
import uuid

from backend.database.session import BASE_DIR


MAX_IMAGE_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000
ALLOWED_IMAGE_MIME_TYPES = frozenset(
    {"image/jpeg", "image/png", "image/webp"}
)
PUBLIC_IMAGE_WIDTHS = (320, 768, 1600)


@dataclass(frozen=True)
class MediaStoragePaths:
    root: Path
    private: Path
    public: Path
    temporary: Path

    @classmethod
    def from_root(cls, root: Path) -> "MediaStoragePaths":
        resolved = root.resolve()
        return cls(
            root=resolved,
            private=resolved / "private",
            public=resolved / "public",
            temporary=resolved / "tmp",
        )

    def ensure_directories(self) -> None:
        for path in (self.root, self.private, self.public, self.temporary):
            path.mkdir(parents=True, exist_ok=True)


DEFAULT_MEDIA_ROOT = BASE_DIR / "data" / "media"


def ensure_within(root: Path, candidate: Path) -> Path:
    resolved_root = root.resolve()
    resolved = candidate.resolve()
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise ValueError("media_path_outside_root")
    return resolved


class MediaFileStore:
    def __init__(self, paths: MediaStoragePaths | None = None):
        self.paths = paths or MediaStoragePaths.from_root(DEFAULT_MEDIA_ROOT)
        self.paths.ensure_directories()

    def asset_file(self, storage_key: str, variant: int | str) -> Path:
        if len(storage_key) != 32 or any(character not in "0123456789abcdef" for character in storage_key):
            raise ValueError("invalid_storage_key")
        if variant == "original":
            base = self.paths.private
            filename = "original.webp"
        elif variant in PUBLIC_IMAGE_WIDTHS:
            base = self.paths.public
            filename = f"{variant}.webp"
        else:
            raise ValueError("invalid_media_variant")
        return ensure_within(base, base / storage_key / filename)

    def remove_asset(self, storage_key: str) -> None:
        for base in (self.paths.private, self.paths.public):
            directory = ensure_within(base, base / storage_key)
            if directory.exists():
                shutil.rmtree(directory)

    def quarantine_asset(self, storage_key: str) -> Path | None:
        sources = [base / storage_key for base in (self.paths.private, self.paths.public)]
        if not any(source.exists() for source in sources):
            return None
        quarantine = ensure_within(
            self.paths.temporary,
            self.paths.temporary / f"delete-{uuid.uuid4().hex}",
        )
        quarantine.mkdir()
        for label, source in zip(("private", "public"), sources, strict=True):
            if source.exists():
                if source.is_symlink():
                    raise ValueError("media_symlink_not_allowed")
                shutil.move(str(source), str(quarantine / label))
        return quarantine

    def restore_quarantine(self, storage_key: str, quarantine: Path | None) -> None:
        if quarantine is None:
            return
        for label, base in (("private", self.paths.private), ("public", self.paths.public)):
            source = quarantine / label
            if source.exists():
                shutil.move(str(source), str(base / storage_key))
        shutil.rmtree(quarantine, ignore_errors=True)

    @staticmethod
    def purge_quarantine(quarantine: Path | None) -> None:
        if quarantine is not None:
            shutil.rmtree(quarantine)
