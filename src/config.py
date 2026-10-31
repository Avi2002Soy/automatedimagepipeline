"""Central configuration, read once from environment / Function App settings."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache

# Output sizes (longest edge, px). Order does not matter; the processor sorts them.
DEFAULT_VARIANTS = {"thumbnail": 128, "small": 480, "medium": 1024}


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required setting: {name}")
    return value


@dataclass(frozen=True)
class Settings:
    storage_connection: str
    raw_container: str
    processed_container: str
    vision_endpoint: str
    vision_key: str | None
    cosmos_endpoint: str
    cosmos_key: str | None
    cosmos_database: str
    cosmos_container: str
    max_upload_bytes: int
    jpeg_quality: int
    min_tag_confidence: float
    variants: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_VARIANTS))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        storage_connection=_require("STORAGE_CONNECTION"),
        raw_container=os.getenv("RAW_CONTAINER", "raw-images"),
        processed_container=os.getenv("PROCESSED_CONTAINER", "processed-images"),
        vision_endpoint=_require("VISION_ENDPOINT"),
        vision_key=os.getenv("VISION_KEY"),  # None -> managed identity
        cosmos_endpoint=_require("COSMOS_ENDPOINT"),
        cosmos_key=os.getenv("COSMOS_KEY"),  # None -> managed identity
        cosmos_database=os.getenv("COSMOS_DATABASE", "imagedb"),
        cosmos_container=os.getenv("COSMOS_CONTAINER", "metadata"),
        max_upload_bytes=int(os.getenv("MAX_UPLOAD_MB", "20")) * 1024 * 1024,
        jpeg_quality=int(os.getenv("JPEG_QUALITY", "85")),
        min_tag_confidence=float(os.getenv("MIN_TAG_CONFIDENCE", "0.6")),
    )
