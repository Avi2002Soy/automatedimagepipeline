import io

import pytest
from PIL import Image


def make_image_bytes(size=(3000, 2000), mode="RGB", fmt="JPEG", color=(120, 80, 200)) -> bytes:
    img = Image.new(mode, size, color if mode == "RGB" else (*color, 128))
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


@pytest.fixture
def jpeg_bytes():
    return make_image_bytes()


@pytest.fixture
def png_alpha_bytes():
    return make_image_bytes(size=(800, 600), mode="RGBA", fmt="PNG")
