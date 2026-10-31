"""Writes resized variants to the processed-images container."""
from __future__ import annotations

import posixpath
from concurrent.futures import ThreadPoolExecutor

from azure.storage.blob import BlobServiceClient, ContentSettings

from .image_processor import ResizedImage
from .models import StoredVariant


class BlobStorage:
    def __init__(self, connection_string: str, processed_container: str):
        self._container_name = processed_container
        self._container = BlobServiceClient.from_connection_string(
            connection_string
        ).get_container_client(processed_container)

    @staticmethod
    def output_name(blob_name: str, variant: str) -> str:
        stem, _ = posixpath.splitext(blob_name)
        return f"{variant}/{stem}.jpg"

    def upload_variants(self, blob_name: str, variants: list[ResizedImage]) -> list[StoredVariant]:
        def _upload(v: ResizedImage) -> StoredVariant:
            path = self.output_name(blob_name, v.variant)
            self._container.upload_blob(
                path,
                v.data,
                overwrite=True,  # idempotent on event re-delivery
                content_settings=ContentSettings(content_type=v.content_type),
            )
            return StoredVariant(v.variant, v.width, v.height, len(v.data),
                                 f"{self._container_name}/{path}")

        with ThreadPoolExecutor(max_workers=len(variants)) as pool:
            return list(pool.map(_upload, variants))
