"""Azure AI Vision (Image Analysis 4.0) wrapper: caption + tags, with retry on throttling."""
from __future__ import annotations

import logging

from azure.ai.vision.imageanalysis import ImageAnalysisClient
from azure.ai.vision.imageanalysis.models import VisualFeatures
from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import HttpResponseError, ServiceRequestError
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from .models import VisionResult

log = logging.getLogger(__name__)
_TRANSIENT_STATUS = {408, 429, 500, 502, 503, 504}


def _is_transient(exc: BaseException) -> bool:
    if isinstance(exc, ServiceRequestError):
        return True
    return isinstance(exc, HttpResponseError) and exc.status_code in _TRANSIENT_STATUS


class VisionAnalyzer:
    def __init__(self, endpoint: str, key: str | None, min_tag_confidence: float = 0.6):
        if key:
            credential = AzureKeyCredential(key)
        else:  # managed identity / az login
            from azure.identity import DefaultAzureCredential

            credential = DefaultAzureCredential()
        self._client = ImageAnalysisClient(endpoint=endpoint, credential=credential)
        self._min_conf = min_tag_confidence

    @retry(
        retry=retry_if_exception(_is_transient),
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
        reraise=True,
    )
    def analyze(self, image_bytes: bytes) -> VisionResult:
        result = self._client.analyze(
            image_data=image_bytes,
            visual_features=[VisualFeatures.CAPTION, VisualFeatures.TAGS],
            gender_neutral_caption=True,
        )
        caption = getattr(result, "caption", None)
        tags = getattr(getattr(result, "tags", None), "list", None) or []
        return VisionResult(
            caption=caption.text if caption else None,
            caption_confidence=round(caption.confidence, 4) if caption else None,
            tags=[
                {"name": t.name, "confidence": round(t.confidence, 4)}
                for t in tags
                if t.confidence >= self._min_conf
            ],
            model_version=getattr(result, "model_version", None),
        )
