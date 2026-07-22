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


def test_put_camera_status_sends_system_token():
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "camera_id": "cam-front",
                "name": "cam-front",
                "stream_type": "ip_rtsp",
                "zone": None,
                "is_online": False,
                "last_seen_at": None,
                "created_at": None,
            },
        )

    transport = httpx.MockTransport(handler)
    client = ApiClient(
        base_url="http://api:8000",
        system_token="secret-token",
        transport=transport,
    )
    client.put_camera_status("cam-front", is_online=False, name="cam-front")

    assert len(calls) == 1
    req = calls[0]
    assert req.method == "PUT"
    assert str(req.url) == "http://api:8000/api/cameras/cam-front"
    assert req.headers.get("X-System-Token") == "secret-token"
    import json

    body = json.loads(req.content.decode())
    assert body["is_online"] is False
    assert body["name"] == "cam-front"
