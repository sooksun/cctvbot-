"""HTTP client for POSTing events to the FastAPI service."""

from __future__ import annotations

from typing import Any

import httpx


class ApiClient:
    def __init__(
        self,
        base_url: str,
        system_token: str,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.system_token = system_token
        self._client = httpx.Client(
            base_url=self.base_url,
            headers={"X-System-Token": system_token},
            transport=transport,
            timeout=timeout,
        )

    def post_event(self, payload: dict[str, Any]) -> None:
        response = self._client.post("/api/events", json=payload)
        response.raise_for_status()

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "ApiClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
