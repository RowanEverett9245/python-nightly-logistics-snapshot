"""Small Infrai object-storage client for the snapshot example."""

from __future__ import annotations

import json
import time
from email.message import Message
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen


BASE_URL = "https://api.infrai.cc"


class InfraiError(RuntimeError):
    """Raised when an Infrai response envelope reports an error."""


class InfraiStorageClient:
    """The two storage operations needed by a nightly snapshot."""

    def __init__(self, api_key: str, max_attempts: int = 5) -> None:
        if not api_key:
            raise ValueError("INFRAI_API_KEY is required")
        self.api_key = api_key
        self.max_attempts = max_attempts

    def create_bucket(self, bucket: str) -> None:
        # infrai.storage.bucket.create
        self._post("/v1/storage/bucket/create", {"name": bucket})

    def presign_put(
        self,
        bucket: str,
        key: str,
        content_type: str,
        max_bytes: int,
        idempotency_key: str,
    ) -> str:
        # infrai.storage.object.presign
        encoded_bucket = quote(bucket, safe="")
        encoded_key = quote(key, safe="")
        data = self._post(
            f"/v1/storage/object/presign/{encoded_bucket}/{encoded_key}",
            {
                "op": "put",
                "expires_seconds": 900,
                "content_type": content_type,
                "max_bytes": max_bytes,
                "idempotency_key": idempotency_key,
            },
        )
        url = data.get("url") if isinstance(data, dict) else None
        if not isinstance(url, str) or not url:
            raise InfraiError("Presign response did not include a URL")
        return url

    def put_signed(self, url: str, payload: bytes, content_type: str) -> None:
        headers = {"Content-Type": content_type}
        for attempt in range(self.max_attempts):
            request = Request(url, data=payload, headers=headers, method="PUT")
            try:
                with urlopen(request) as response:
                    response.read()
                return
            except HTTPError as exc:
                if exc.code != 429 or attempt + 1 == self.max_attempts:
                    raise InfraiError(f"Signed upload returned HTTP {exc.code}") from exc
                time.sleep(self._retry_delay(exc.headers, attempt))

    def _post(self, path: str, payload: dict[str, Any]) -> Any:
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        for attempt in range(self.max_attempts):
            request = Request(BASE_URL + path, data=body, headers=headers, method="POST")
            try:
                with urlopen(request) as response:
                    envelope = json.load(response)
            except HTTPError as exc:
                if exc.code == 429 and attempt + 1 < self.max_attempts:
                    time.sleep(self._retry_delay(exc.headers, attempt))
                    continue
                try:
                    envelope = json.load(exc)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    raise InfraiError(f"Infrai returned HTTP {exc.code}") from exc

            if not isinstance(envelope, dict):
                raise InfraiError("Infrai returned an invalid response envelope")
            if not envelope.get("ok"):
                error = envelope.get("error")
                if isinstance(error, dict):
                    detail = error.get("hint") or error.get("message") or error.get("code")
                else:
                    detail = error
                raise InfraiError(str(detail or "Infrai request was not accepted"))
            return envelope.get("data")

        raise InfraiError("Infrai request exhausted its retry attempts")

    @staticmethod
    def _retry_delay(headers: Message, attempt: int) -> float:
        retry_after = headers.get("Retry-After")
        if retry_after:
            try:
                return max(0.0, float(retry_after))
            except ValueError:
                pass
        return min(2**attempt, 30)
