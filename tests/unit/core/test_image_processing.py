from io import BytesIO

import pytest
from PIL import Image

from backend.core.image_processing import ImageProcessingError, SafeImageProcessor
from backend.core.media_storage import MAX_IMAGE_UPLOAD_BYTES, MediaFileStore, MediaStoragePaths


def image_bytes(format="JPEG", size=(640, 480), mode="RGB", exif=None):
    image = Image.new(mode, size, (40, 120, 200, 180) if mode == "RGBA" else (40, 120, 200))
    output = BytesIO()
    kwargs = {"exif": exif} if exif else {}
    image.save(output, format=format, **kwargs)
    return output.getvalue()


@pytest.fixture
def processor(tmp_path):
    return SafeImageProcessor(MediaFileStore(MediaStoragePaths.from_root(tmp_path / "media")))


@pytest.mark.parametrize(("format", "mime"), [("JPEG", "image/jpeg"), ("PNG", "image/png"), ("WEBP", "image/webp")])
def test_processes_supported_images_and_variants(processor, format, mime):
    result = processor.process(image_bytes(format, mode="RGBA" if format == "PNG" else "RGB"), mime)

    assert result.mime_type == "image/webp"
    assert len(result.checksum_sha256) == 64
    for variant in ("original", 320, 768, 1600):
        path = processor.store.asset_file(result.storage_key, variant)
        assert path.is_file()
        with Image.open(path) as image:
            assert image.format == "WEBP"
            assert image.width <= (640 if variant == "original" else min(640, variant))
            assert image.getexif() == {}


def test_corrects_exif_orientation_and_removes_metadata(processor):
    exif = Image.Exif()
    exif[274] = 6
    exif[315] = "private author"
    result = processor.process(image_bytes("JPEG", (120, 80), exif=exif), "image/jpeg")

    assert (result.width, result.height) == (80, 120)
    with Image.open(processor.store.asset_file(result.storage_key, "original")) as normalized:
        assert normalized.size == (80, 120)
        assert normalized.getexif() == {}


def test_small_image_is_not_upscaled(processor):
    result = processor.process(image_bytes("PNG", (90, 60)), "image/png")
    for width in (320, 768, 1600):
        with Image.open(processor.store.asset_file(result.storage_key, width)) as image:
            assert image.size == (90, 60)


def test_rejects_mime_mismatch_and_cleans_tmp(processor):
    with pytest.raises(ImageProcessingError, match="media_mime_mismatch"):
        processor.process(image_bytes("PNG"), "image/jpeg")
    assert list(processor.store.paths.temporary.iterdir()) == []
    assert list(processor.store.paths.public.iterdir()) == []


@pytest.mark.parametrize("content", [b"not an image", b"<svg></svg>"])
def test_rejects_corrupt_and_svg_content(processor, content):
    with pytest.raises(ImageProcessingError):
        processor.process(content, "image/png")


def test_rejects_animated_webp(processor):
    frames = [Image.new("RGB", (10, 10), color) for color in ("red", "blue")]
    output = BytesIO()
    frames[0].save(output, "WEBP", save_all=True, append_images=frames[1:], duration=100)
    with pytest.raises(ImageProcessingError, match="media_animated_not_allowed"):
        processor.process(output.getvalue(), "image/webp")


def test_rejects_more_than_ten_mib_before_decode(processor):
    with pytest.raises(ImageProcessingError, match="media_file_too_large"):
        processor.process(b"x" * (MAX_IMAGE_UPLOAD_BYTES + 1), "image/jpeg")


def test_accepts_exactly_ten_mib_when_content_is_valid(processor):
    content = image_bytes("JPEG")
    content += b"\0" * (MAX_IMAGE_UPLOAD_BYTES - len(content))
    assert len(content) == MAX_IMAGE_UPLOAD_BYTES
    assert processor.process(content, "image/jpeg").width == 640


def test_rejects_more_than_forty_million_pixels(processor):
    image = Image.new("1", (8000, 5001))
    output = BytesIO()
    image.save(output, "PNG")
    with pytest.raises(ImageProcessingError, match="media_too_many_pixels"):
        processor.process(output.getvalue(), "image/png")


def test_path_traversal_and_unknown_variant_are_rejected(processor):
    with pytest.raises(ValueError, match="invalid_storage_key"):
        processor.store.asset_file("../../outside", 320)
    with pytest.raises(ValueError, match="invalid_media_variant"):
        processor.store.asset_file("a" * 32, 999)
