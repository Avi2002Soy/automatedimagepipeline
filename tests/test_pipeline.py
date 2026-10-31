from src.config import DEFAULT_VARIANTS
from src.models import StoredVariant, VisionResult, make_document_id
from src.pipeline import ImagePipeline


class FakeStorage:
    def upload_variants(self, blob_name, variants):
        return [StoredVariant(v.variant, v.width, v.height, len(v.data), f"p/{v.variant}/{blob_name}")
                for v in variants]


class FakeVision:
    def analyze(self, image_bytes):
        return VisionResult(caption="a purple rectangle", caption_confidence=0.9,
                            tags=[{"name": "purple", "confidence": 0.95}])


class BrokenVision:
    def analyze(self, image_bytes):
        raise RuntimeError("429 throttled")


class FakeRepo:
    def __init__(self):
        self.docs = {}

    def upsert(self, document):
        self.docs[document["id"]] = document


def _pipeline(vision):
    repo = FakeRepo()
    return ImagePipeline(storage=FakeStorage(), vision=vision, repository=repo,
                         variants=DEFAULT_VARIANTS), repo


def test_happy_path(jpeg_bytes):
    pipe, repo = _pipeline(FakeVision())
    doc = pipe.handle("raw-images/a.jpg", jpeg_bytes)
    assert doc["status"] == "processed"
    assert doc["vision"]["caption"] == "a purple rectangle"
    assert len(doc["variants"]) == 3
    assert doc["id"] == make_document_id("raw-images", "a.jpg")
    assert doc["id"] in repo.docs


def test_vision_failure_is_partial_not_fatal(jpeg_bytes):
    pipe, _ = _pipeline(BrokenVision())
    doc = pipe.handle("raw-images/a.jpg", jpeg_bytes)
    assert doc["status"] == "partial"
    assert "vision_failed" in doc["error"]
    assert len(doc["variants"]) == 3


def test_invalid_file_rejected_and_recorded():
    pipe, repo = _pipeline(FakeVision())
    doc = pipe.handle("raw-images/readme.txt", b"hello")
    assert doc["status"] == "rejected"
    assert repo.docs


def test_redelivery_is_idempotent(jpeg_bytes):
    pipe, repo = _pipeline(FakeVision())
    pipe.handle("raw-images/a.jpg", jpeg_bytes)
    pipe.handle("raw-images/a.jpg", jpeg_bytes)
    assert len(repo.docs) == 1
