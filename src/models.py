"""Plain data models and the Cosmos document schema."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_document_id(container: str, blob_name: str) -> str:
    """Deterministic id => re-delivered events overwrite the same document (idempotent)."""
    return hashlib.sha256(f"{container}/{blob_name}".encode()).hexdigest()[:32]


@dataclass
class VisionResult:
    caption: str | None = None
    caption_confidence: float | None = None
    tags: list[dict[str, Any]] = field(default_factory=list)  # [{"name":..., "confidence":...}]
    model_version: str | None = None


@dataclass
class StoredVariant:
    name: str
    width: int
    height: int
    size_bytes: int
    blob_path: str  # "<container>/<variant>/<name>.jpg"


def build_document(
    *,
    doc_id: str,
    container: str,
    blob_name: str,
    status: str,  # processed | partial | rejected
    original: dict[str, Any] | None = None,
    variants: list[StoredVariant] | None = None,
    vision: VisionResult | None = None,
    error: str | None = None,
    metrics: dict[str, float] | None = None,
) -> dict[str, Any]:
    return {
        "id": doc_id,
        "blobName": blob_name,
        "sourceContainer": container,
        "status": status,
        "processedAt": utc_now_iso(),
        "original": original,
        "variants": [v.__dict__ for v in (variants or [])],
        "vision": (
            {
                "caption": vision.caption,
                "captionConfidence": vision.caption_confidence,
                "tags": vision.tags,
                "modelVersion": vision.model_version,
            }
            if vision
            else None
        ),
        "error": error,
        "metrics": metrics or {},
    }
