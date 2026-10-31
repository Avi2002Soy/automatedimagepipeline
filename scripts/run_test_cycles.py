"""End-to-end test: upload N synthetic images, wait for the pipeline, report success rate.

    python -m scripts.run_test_cycles --count 100

Needs the same env vars as the Function App (STORAGE_CONNECTION, COSMOS_*).
Success = Cosmos document reaches status 'processed' (resize + Vision + metadata all OK).
"""
import argparse
import os
import random
import time
import uuid
from collections import Counter

from azure.cosmos import CosmosClient
from azure.cosmos.exceptions import CosmosResourceNotFoundError
from azure.storage.blob import BlobServiceClient

from scripts.benchmark_resize import synthetic_jpeg
from src.models import make_document_id


def main(count: int, timeout: int) -> None:
    raw = os.getenv("RAW_CONTAINER", "raw-images")
    blobs = BlobServiceClient.from_connection_string(os.environ["STORAGE_CONNECTION"]).get_container_client(raw)
    cosmos = (CosmosClient(os.environ["COSMOS_ENDPOINT"], os.environ["COSMOS_KEY"])
              .get_database_client(os.getenv("COSMOS_DATABASE", "imagedb"))
              .get_container_client(os.getenv("COSMOS_CONTAINER", "metadata")))

    run = uuid.uuid4().hex[:8]
    names = [f"test-{run}/img-{i:03d}.jpg" for i in range(count)]
    for n in names:
        blobs.upload_blob(n, synthetic_jpeg(random.choice([1280, 2048, 4000]), random.choice([960, 1536, 3000])))
    print(f"Uploaded {count} images (run {run}); waiting up to {timeout}s ...")

    status, resize_ms, deadline = {}, [], time.time() + timeout
    while time.time() < deadline and len(status) < count:
        for n in names:
            if n in status:
                continue
            doc_id = make_document_id(raw, n)
            try:
                doc = cosmos.read_item(doc_id, partition_key=doc_id)
                status[n] = doc["status"]
                resize_ms.append(doc["metrics"].get("resizeMs", 0))
            except CosmosResourceNotFoundError:
                pass
        time.sleep(2)

    counts = Counter(status.get(n, "timeout") for n in names)
    ok = counts.get("processed", 0)
    print(dict(counts))
    print(f"Success rate: {ok}/{count} = {ok / count:.0%}")
    if resize_ms:
        print(f"Avg resize time: {sum(resize_ms) / len(resize_ms):.1f} ms")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=100)
    ap.add_argument("--timeout", type=int, default=180)
    main(**vars(ap.parse_args()))
