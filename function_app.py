"""Azure Functions entry point (Python v2 programming model). Kept thin: wiring only."""
from __future__ import annotations

import json
import logging
from functools import lru_cache

import azure.functions as func

app = func.FunctionApp()


@lru_cache(maxsize=1)
def _deps():
    """Clients are created once per worker and reused across warm invocations."""
    from src.blob_service import BlobStorage
    from src.config import get_settings
    from src.cosmos_repository import MetadataRepository
    from src.pipeline import ImagePipeline
    from src.vision_service import VisionAnalyzer

    s = get_settings()
    repo = MetadataRepository(s.cosmos_endpoint, s.cosmos_key, s.cosmos_database, s.cosmos_container)
    pipeline = ImagePipeline(
        storage=BlobStorage(s.storage_connection, s.processed_container),
        vision=VisionAnalyzer(s.vision_endpoint, s.vision_key, s.min_tag_confidence),
        repository=repo,
        variants=s.variants,
        jpeg_quality=s.jpeg_quality,
        max_upload_bytes=s.max_upload_bytes,
    )
    return pipeline, repo


# --------------------------------------------------------------------------------------
# 1) Event-driven processing: Blob Created -> Event Grid -> this function
#    source="EventGrid" = push-based (near-instant) instead of slow blob polling.
# --------------------------------------------------------------------------------------
@app.function_name("process_image")
@app.blob_trigger(arg_name="blob", path="raw-images/{name}",
                  connection="STORAGE_CONNECTION", source="EventGrid")
def process_image(blob: func.InputStream) -> None:
    pipeline, _ = _deps()
    logging.info("Event received for %s (%s bytes)", blob.name, blob.length)
    pipeline.handle(blob.name, blob.read())


# --------------------------------------------------------------------------------------
# 2) Read API for real-time apps (dashboards, galleries, search boxes)
# --------------------------------------------------------------------------------------
def _json(body, status=200) -> func.HttpResponse:
    return func.HttpResponse(json.dumps(body), status_code=status, mimetype="application/json")


@app.function_name("get_image")
@app.route(route="images/{image_id}", methods=["GET"], auth_level=func.AuthLevel.FUNCTION)
def get_image(req: func.HttpRequest) -> func.HttpResponse:
    _, repo = _deps()
    doc = repo.get(req.route_params["image_id"])
    return _json(doc) if doc else _json({"error": "not found"}, 404)


@app.function_name("search_images")
@app.route(route="images", methods=["GET"], auth_level=func.AuthLevel.FUNCTION)
def search_images(req: func.HttpRequest) -> func.HttpResponse:
    tag = req.params.get("tag")
    if not tag:
        return _json({"error": "query parameter 'tag' is required"}, 400)
    limit = min(int(req.params.get("limit", "20")), 100)
    _, repo = _deps()
    return _json(repo.search_by_tag(tag, limit))
