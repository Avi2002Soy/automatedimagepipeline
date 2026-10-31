"""Measure Pillow resize latency locally (no Azure needed) to back up the '<200 ms' claim.

    python -m scripts.benchmark_resize --runs 50 --width 4000 --height 3000
"""
import argparse
import io
import random
import statistics

from PIL import Image, ImageDraw

from src.config import DEFAULT_VARIANTS
from src.image_processor import process_image


def synthetic_jpeg(w: int, h: int) -> bytes:
    img = Image.new("RGB", (w, h), (30, 60, 90))
    d = ImageDraw.Draw(img)
    for _ in range(60):
        x, y = random.randint(0, w), random.randint(0, h)
        r = random.randint(20, 400)
        d.ellipse((x, y, x + r, y + r), fill=tuple(random.randint(0, 255) for _ in range(3)))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=92)
    return buf.getvalue()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=50)
    ap.add_argument("--width", type=int, default=4000)
    ap.add_argument("--height", type=int, default=3000)
    a = ap.parse_args()

    data = synthetic_jpeg(a.width, a.height)
    process_image(data, DEFAULT_VARIANTS)  # warm-up
    times = sorted(process_image(data, DEFAULT_VARIANTS).elapsed_ms for _ in range(a.runs))
    print(f"input {a.width}x{a.height}  {len(data)/1e6:.2f} MB  runs={a.runs}")
    print(f"mean={statistics.mean(times):.1f} ms  median={statistics.median(times):.1f} ms  "
          f"p95={times[int(0.95 * len(times)) - 1]:.1f} ms  max={times[-1]:.1f} ms")
