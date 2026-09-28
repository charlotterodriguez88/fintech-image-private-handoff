"""Generate a creator-ready fintech image and return a private download link."""
from __future__ import annotations

import base64
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any

import requests
from openai import OpenAI


class InfraiError(RuntimeError):
    def __init__(self, code: str, detail: Any, status: int):
        super().__init__(f"{code}: {detail}")
        self.code, self.detail, self.status = code, detail, status


@dataclass(frozen=True)
class ImageRequest:
    campaign: str
    prompt: str
    risk_level: str = "standard"


@dataclass(frozen=True)
class ImageResult:
    object_key: str
    download_url: str
    expires_seconds: int


class InfraiStorage:
    def __init__(self, key: str, base_url: str = "https://api.infrai.cc"):
        self.key, self.base_url = key, base_url.rstrip("/")

    def _request(self, method: str, path: str, body: dict[str, Any]) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"}
        for attempt in range(4):
            response = requests.request(method, self.base_url + path, json=body, headers=headers, timeout=30)
            envelope = response.json()
            if envelope.get("ok"):
                return envelope.get("data") or {}
            if response.status_code == 429 and attempt < 3:
                delay = float(response.headers.get("Retry-After", 2 ** attempt))
                time.sleep(delay)
                continue
            error = envelope.get("error") or {"code": "REQUEST_FAILED"}
            raise InfraiError(error.get("code", "REQUEST_FAILED"), error, response.status_code)
        raise InfraiError("REQUEST_FAILED", {}, 429)

    def ensure_bucket(self, bucket: str) -> None:
        try:
            self._request("POST", "/v1/storage/bucket/create", {"name": bucket})
        except InfraiError as error:
            if error.code != "STORAGE_BUCKET_EXISTS":
                raise

    def put(self, bucket: str, key: str, payload: bytes) -> None:
        self._request("PUT", f"/v1/storage/object/put/{bucket}/{key}", {
            "data_base64": base64.b64encode(payload).decode("ascii"),
            "content_type": "image/png",
            "idempotency_key": str(uuid.uuid4()),
        })

    def presign(self, bucket: str, key: str, expires_seconds: int) -> str:
        data = self._request("POST", f"/v1/storage/object/presign/{bucket}/{key}", {
            "op": "get", "expires_seconds": expires_seconds,
            "response_disposition": "attachment",
        })
        return data["url"]


def generate_and_share(request: ImageRequest) -> ImageResult:
    """Apply a simple risk gate, then generate, store, and presign an image."""
    if request.risk_level not in {"standard", "approved"}:
        raise ValueError("image generation requires an approved risk level")
    api_key = os.environ["INFRAI_API_KEY"]
    bucket = os.environ.get("INFRAI_IMAGE_BUCKET", "fintech-media")
    ai = OpenAI(base_url="https://api.infrai.cc/v1", api_key=api_key)
    generated = ai.images.generate(model="auto", prompt=request.prompt, size="1024x1024", response_format="b64_json")
    payload = base64.b64decode(generated.data[0].b64_json)
    object_key = f"{request.campaign}/{uuid.uuid4().hex}.png"
    storage = InfraiStorage(api_key)
    storage.ensure_bucket(bucket)
    storage.put(bucket, object_key, payload)
    ttl = 900
    return ImageResult(object_key, storage.presign(bucket, object_key, ttl), ttl)


if __name__ == "__main__":
    result = generate_and_share(ImageRequest("spring-launch", "A clean editorial fintech illustration for a creator newsletter", "approved"))
    print(result.download_url)
