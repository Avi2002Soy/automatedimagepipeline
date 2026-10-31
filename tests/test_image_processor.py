import io

import pytest
from PIL import Image

from src.config import DEFAULT_VARIANTS
from src.image_processor import UnsupportedImageError, process_image
from tests.conftest import make_image_bytes


def test_produces_all_variants_within_bounds(jpeg_bytes):
    result = process_image(jpeg_bytes, DEFAULT_VARIANTS)
    assert {v.variant for v in result.variants} == set(DEFAULT_VARIANTS)
    for v in result.variants:
        assert max(v.width, v.height) <= DEFAULT_VARIANTS[v.variant]
        assert Image.open(io.BytesIO(v.data)).format == "JPEG"
    assert (result.original_width, result.original_height) == (3000, 2000)


def test_aspect_ratio_preserved(jpeg_bytes):
    medium = next(v for v in process_image(jpeg_bytes, DEFAULT_VARIANTS).variants
                  if v.variant == "medium")
    assert abs(medium.width / medium.height - 1.5) < 0.01


def test_never_upscales():
    tiny = make_image_bytes(size=(60, 40))
    for v in process_image(tiny, DEFAULT_VARIANTS).variants:
        assert (v.width, v.height) == (60, 40)


def test_png_with_alpha_is_flattened(png_alpha_bytes):
    result = process_image(png_alpha_bytes, DEFAULT_VARIANTS)
    assert Image.open(io.BytesIO(result.variants[0].data)).mode == "RGB"


def test_garbage_bytes_rejected():
    with pytest.raises(UnsupportedImageError):
        process_image(b"not an image", DEFAULT_VARIANTS)


def test_unsupported_format_rejected():
    ico = make_image_bytes(size=(32, 32), fmt="ICO")
    with pytest.raises(UnsupportedImageError):
        process_image(ico, DEFAULT_VARIANTS)
