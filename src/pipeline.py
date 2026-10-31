"""Orchestration: resize -> (upload variants || AI Vision) -> persist metadata.

Deliberately free of Azure imports; collaborators are injected, so it is unit-testable with fakes.

Failure policy
  * Not an image / too big      -> status "rejected" (stored, no retry: retrying cannot help)
  * Vision fails after retries  -> status "partial"  (resized images + record are still kept)
  * Blob/Cosmos write fails     -> exception propagates => Event Grid re-delivers the event
                                   (at-least-once; safe because ids and blob paths are deterministic)
"""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Protocol

from .image_processor import ResizedImage, UnsupportedImageError, process_image
from .models import StoredVariant, VisionResult, build_document, make_document_id

log = logging.getLogger(__name__)


class Storage(Protocol):
    def upload_variants(self, blob_name: str, variants: list[ResizedImage]) -> list[StoredVariant]: ...


class Vision(Protocol):
    def analyze(self, image_bytes: bytes) -> VisionResult: ...


class Repository(Protocol):
    def upsert(self, document: dict[str, Any]) -> None: ...


class ImagePipeline:
    def __init__(self, *, storage: Storage, vision: Vision, repository: Repository,
                 variants: dict[str, int], jpeg_quality: int = 85,
                 max_upload_bytes: int = 20 * 1024 * 1024):
        self.storage, self.vision, self.repo = storage, vision, repository
        self.variants, self.quality, self.max_bytes = variants, jpeg_quality, max_upload_bytes

    def handle(self, blob_path: str, data: bytes) -> dict[str, Any]:
        """blob_path looks like 'raw-images/holiday/photo1.png'."""
        started = time.perf_counter()
        container, _, blob_name = blob_path.partition("/")
        doc_id = make_document_id(container, blob_name)
        base = dict(doc_id=doc_id, container=container, blob_name=blob_name)

        if len(data) > self.max_bytes:
            return self._save(build_document(**base, status="rejected",
                                             error=f"File exceeds {self.max_bytes} bytes"))
        try:
            resized = process_image(data, self.variants, self.quality)
        except UnsupportedImageError as exc:
            log.warning("Rejected %s: %s", blob_path, exc)
            return self._save(build_document(**base, status="rejected", error=str(exc)))

        original = {"format": resized.original_format, "width": resized.original_width,
                    "height": resized.original_height, "sizeBytes": resized.original_size_bytes}
        largest = resized.variants[0]  # sorted large -> small; send the reduced image to Vision

        vision_ms = 0.0
        with ThreadPoolExecutor(max_workers=2) as pool:
            upload_f = pool.submit(self.storage.upload_variants, blob_name, resized.variants)
            vision_f = pool.submit(self._timed_vision, largest.data)
            stored = upload_f.result()  # raises -> Event Grid retry
            vision, vision_err, vision_ms = vision_f.result()

        doc = build_document(
            **base,
            status="processed" if vision else "partial",
            original=original,
            variants=stored,
            vision=vision,
            error=vision_err,
            metrics={"resizeMs": round(resized.elapsed_ms, 1), "visionMs": round(vision_ms, 1),
                     "totalMs": round((time.perf_counter() - started) * 1000, 1)},
        )
        log.info("Processed %s resize=%.0fms vision=%.0fms status=%s", blob_path,
                 resized.elapsed_ms, vision_ms, doc["status"])
        return self._save(doc)

    def _timed_vision(self, image_bytes: bytes) -> tuple[VisionResult | None, str | None, float]:
        t0 = time.perf_counter()
        try:
            return self.vision.analyze(image_bytes), None, (time.perf_counter() - t0) * 1000
        except Exception as exc:  # noqa: BLE001 - degrade gracefully, keep the resized output
            log.exception("Vision analysis failed")
            return None, f"vision_failed: {exc}", (time.perf_counter() - t0) * 1000

    def _save(self, doc: dict[str, Any]) -> dict[str, Any]:
        self.repo.upsert(doc)
        return doc
