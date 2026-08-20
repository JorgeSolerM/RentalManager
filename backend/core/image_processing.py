from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import shutil
import uuid

from PIL import Image, ImageOps, UnidentifiedImageError

from backend.core.media_storage import (
    ALLOWED_IMAGE_MIME_TYPES,
    MAX_IMAGE_PIXELS,
    MAX_IMAGE_UPLOAD_BYTES,
    PUBLIC_IMAGE_WIDTHS,
    MediaFileStore,
    ensure_within,
)


FORMAT_MIME = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}


class ImageProcessingError(ValueError):
    pass


@dataclass(frozen=True)
class ProcessedImage:
    storage_key: str
    mime_type: str
    width: int
    height: int
    byte_size: int
    checksum_sha256: str


class SafeImageProcessor:
    def __init__(self, store: MediaFileStore | None = None):
        self.store = store or MediaFileStore()

    def process(self, content: bytes, declared_mime: str | None = None) -> ProcessedImage:
        if not content or len(content) > MAX_IMAGE_UPLOAD_BYTES:
            raise ImageProcessingError("media_file_too_large" if content else "media_invalid_image")
        staging = ensure_within(
            self.store.paths.temporary,
            self.store.paths.temporary / f"upload-{uuid.uuid4().hex}",
        )
        storage_key = uuid.uuid4().hex
        try:
            staging.mkdir()
            image_format, image = self._decode(content)
            actual_mime = FORMAT_MIME[image_format]
            if declared_mime and declared_mime.lower() not in ALLOWED_IMAGE_MIME_TYPES:
                raise ImageProcessingError("media_unsupported_format")
            if declared_mime and declared_mime.lower() != actual_mime:
                raise ImageProcessingError("media_mime_mismatch")

            normalized = ImageOps.exif_transpose(image)
            normalized.load()
            normalized = normalized.convert("RGBA" if "A" in normalized.getbands() else "RGB")
            width, height = normalized.size
            if width <= 0 or height <= 0 or width * height > MAX_IMAGE_PIXELS:
                raise ImageProcessingError("media_too_many_pixels")

            original = staging / "original.webp"
            self._save_webp(normalized, original, quality=95)
            original_bytes = original.read_bytes()
            for target_width in PUBLIC_IMAGE_WIDTHS:
                variant = normalized.copy()
                if variant.width > target_width:
                    target_height = max(1, round(variant.height * target_width / variant.width))
                    variant.thumbnail((target_width, target_height), Image.Resampling.LANCZOS)
                self._save_webp(variant, staging / f"{target_width}.webp", quality=86)

            private_dir = self.store.paths.private / storage_key
            public_dir = self.store.paths.public / storage_key
            private_dir.mkdir()
            public_dir.mkdir()
            shutil.move(str(original), str(private_dir / "original.webp"))
            for target_width in PUBLIC_IMAGE_WIDTHS:
                shutil.move(str(staging / f"{target_width}.webp"), str(public_dir / f"{target_width}.webp"))
            return ProcessedImage(
                storage_key=storage_key,
                mime_type="image/webp",
                width=width,
                height=height,
                byte_size=len(original_bytes),
                checksum_sha256=sha256(original_bytes).hexdigest(),
            )
        except ImageProcessingError:
            self.store.remove_asset(storage_key)
            raise
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
            self.store.remove_asset(storage_key)
            raise ImageProcessingError("media_invalid_image") from exc
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    @staticmethod
    def _decode(content: bytes) -> tuple[str, Image.Image]:
        try:
            probe = Image.open(BytesIO(content))
            image_format = (probe.format or "").upper()
            if image_format not in FORMAT_MIME:
                raise ImageProcessingError("media_unsupported_format")
            if getattr(probe, "is_animated", False) or getattr(probe, "n_frames", 1) != 1:
                raise ImageProcessingError("media_animated_not_allowed")
            if probe.width * probe.height > MAX_IMAGE_PIXELS:
                raise ImageProcessingError("media_too_many_pixels")
            probe.verify()
            image = Image.open(BytesIO(content))
            if getattr(image, "is_animated", False) or getattr(image, "n_frames", 1) != 1:
                raise ImageProcessingError("media_animated_not_allowed")
            return image_format, image
        except ImageProcessingError:
            raise
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
            raise ImageProcessingError("media_invalid_image") from exc

    @staticmethod
    def _save_webp(image: Image.Image, path: Path, quality: int) -> None:
        image.save(path, format="WEBP", quality=quality, method=6, exif=b"")
