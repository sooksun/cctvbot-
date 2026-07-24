from fastapi.testclient import TestClient


def test_login_admin_ok(client: TestClient):
    r = client.post("/api/auth/login", json={"username": "admin", "password": "admin123!"})
    assert r.status_code == 200
    body = r.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"
    assert body["role"] == "admin"


def test_login_bad_password(client: TestClient):
    r = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    assert r.status_code == 401


def test_login_unknown_user(client: TestClient):
    r = client.post("/api/auth/login", json={"username": "nobody", "password": "admin123!"})
    assert r.status_code == 401


def test_jwt_allows_authenticated_user(client: TestClient):
    login = client.post("/api/auth/login", json={"username": "admin", "password": "admin123!"})
    token = login.json()["access_token"]
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["username"] == "admin"
    assert r.json()["role"] == "admin"


def test_jwt_missing_returns_401(client: TestClient):
    r = client.get("/api/auth/me")
    assert r.status_code == 401


def test_system_token_ok(client: TestClient):
    r = client.get("/api/auth/system-check", headers={"X-System-Token": "test-system-token"})
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_system_token_bad(client: TestClient):
    r = client.get("/api/auth/system-check", headers={"X-System-Token": "nope"})
    assert r.status_code == 401
