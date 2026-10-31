"""Pure-Python image resizing with Pillow. No Azure dependencies => easy to test/benchmark.

Performance notes (why this can stay well under ~200 ms for typical photos):
  * JPEG ``draft()`` lets libjpeg decode at 1/2, 1/4 or 1/8 scale directly.
  * Variants are produced in cascade (large -> small), so each resize starts from a smaller image.
  * ``reducing_gap`` makes Pillow use a fast box-reduce before the LANCZOS pass.
"""
from __future__ import annotations

import io
import time
from dataclasses import dataclass

from PIL import Image, ImageOps, UnidentifiedImageError

# Guard against decompression bombs (Pillow raises DecompressionBombError at 2x this value).
Image.MAX_IMAGE_PIXELS = 50_000_000

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "BMP", "TIFF", "GIF"}


class UnsupportedImageError(Exception):
    """Raised when the bytes are not a valid / supported image."""


@dataclass
class ResizedImage:
    variant: str
    width: int
    height: int
    data: bytes
    content_type: str = "image/jpeg"


@dataclass
class ProcessingResult:
    original_format: str
    original_width: int
    original_height: int
    original_size_bytes: int
    variants: list[ResizedImage]
    elapsed_ms: float


def _flatten_to_rgb(img: Image.Image) -> Image.Image:
    """JPEG has no alpha: paste transparent images onto white."""
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.getchannel("A"))
        return background
    return img.convert("RGB") if img.mode != "RGB" else img


def process_image(data: bytes, variants: dict[str, int], quality: int = 85) -> ProcessingResult:
    start = time.perf_counter()
    try:
        with Image.open(io.BytesIO(data)) as src:
            fmt = src.format or ""
            if fmt not in ALLOWED_FORMATS:
                raise UnsupportedImageError(f"Unsupported image format: {fmt or 'unknown'}")

            orig_w, orig_h = src.size
            largest = max(variants.values())
            if fmt == "JPEG":
                src.draft("RGB", (largest, largest))  # fast reduced-size decode
            src.load()
            img = _flatten_to_rgb(ImageOps.exif_transpose(src))
    except UnsupportedImageError:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError) as exc:
        raise UnsupportedImageError(f"Cannot decode image: {exc}") from exc

    outputs: list[ResizedImage] = []
    current = img
    for name, size in sorted(variants.items(), key=lambda kv: kv[1], reverse=True):
        resized = current.copy()
        resized.thumbnail((size, size), Image.Resampling.LANCZOS, reducing_gap=2.0)  # never upscales
        buf = io.BytesIO()
        resized.save(buf, format="JPEG", quality=quality, optimize=True, progressive=True)
        outputs.append(ResizedImage(name, resized.width, resized.height, buf.getvalue()))
        current = resized  # cascade

    return ProcessingResult(
        original_format=fmt,
        original_width=orig_w,
        original_height=orig_h,
        original_size_bytes=len(data),
        variants=outputs,
        elapsed_ms=(time.perf_counter() - start) * 1000,
    )
