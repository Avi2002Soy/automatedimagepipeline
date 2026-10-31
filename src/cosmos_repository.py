"""Cosmos DB access. Partition key is /id: high cardinality spreads writes evenly and makes
point reads (read_item) the cheapest possible operation for real-time lookups."""
from __future__ import annotations

from typing import Any

from azure.cosmos import CosmosClient
from azure.cosmos.exceptions import CosmosResourceNotFoundError


class MetadataRepository:
    def __init__(self, endpoint: str, key: str | None, database: str, container: str):
        if key:
            credential: Any = key
        else:
            from azure.identity import DefaultAzureCredential

            credential = DefaultAzureCredential()
        client = CosmosClient(endpoint, credential=credential)
        self._container = client.get_database_client(database).get_container_client(container)

    def upsert(self, document: dict[str, Any]) -> None:
        self._container.upsert_item(document)

    def get(self, doc_id: str) -> dict[str, Any] | None:
        try:
            return self._container.read_item(item=doc_id, partition_key=doc_id)
        except CosmosResourceNotFoundError:
            return None

    def search_by_tag(self, tag: str, limit: int = 20) -> list[dict[str, Any]]:
        query = (
            "SELECT TOP @limit c.id, c.blobName, c.vision.caption, c.vision.tags, c.variants "
            "FROM c WHERE c.status IN ('processed','partial') "
            "AND ARRAY_CONTAINS(c.vision.tags, {'name': @tag}, true) "
            "ORDER BY c.processedAt DESC"
        )
        return list(
            self._container.query_items(
                query=query,
                parameters=[{"name": "@tag", "value": tag.lower()},
                            {"name": "@limit", "value": limit}],
                enable_cross_partition_query=True,
            )
        )
