import httpx
import pytest

from worker.api_client import ApiClient


def test_post_event_sends_system_token(httpx_mock=None):
    """post_event includes X-System-Token and POSTs to /api/events."""
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(201, json={"event_id": "EVT-20260722-0001"})

    transport = httpx.MockTransport(handler)
    client = ApiClient(
        base_url="http://api:8000",
        system_token="secret-token",
        transport=transport,
    )
    payload = {"event_id": "EVT-20260722-0001", "message_th": "ทดสอบ"}
    client.post_event(payload)

    assert len(calls) == 1
    req = calls[0]
    assert req.method == "POST"
    assert str(req.url) == "http://api:8000/api/events"
    assert req.headers.get("X-System-Token") == "secret-token"


def test_post_event_raises_on_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    transport = httpx.MockTransport(handler)
    client = ApiClient(
        base_url="http://api:8000",
        system_token="secret-token",
        transport=transport,
    )
    with pytest.raises(httpx.HTTPStatusError):
        client.post_event({"event_id": "x"})
