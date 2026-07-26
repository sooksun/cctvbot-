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


def test_login_rate_limited(client: TestClient):
    # 10 attempts allowed (wrong password → 401), the 11th is throttled → 429.
    last = None
    for _ in range(11):
        last = client.post(
            "/api/auth/login", json={"username": "admin", "password": "wrong"}
        )
    assert last is not None
    assert last.status_code == 429


def _make_login(client, username, password, role="viewer"):
    from app.auth import hash_password
    from app.db import SessionLocal
    from app.models import User

    db = SessionLocal()
    try:
        u = db.query(User).filter(User.username == username).first()
        if u:
            u.password_hash = hash_password(password)
        else:
            db.add(User(username=username, password_hash=hash_password(password), role=role))
        db.commit()
    finally:
        db.close()
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200
    return r.json()["access_token"]


def test_change_password_success(client: TestClient):
    token = _make_login(client, "pwuser", "oldpass123")
    h = {"Authorization": f"Bearer {token}"}
    r = client.post(
        "/api/auth/change-password",
        json={"current_password": "oldpass123", "new_password": "newpass456"},
        headers=h,
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert client.post(
        "/api/auth/login", json={"username": "pwuser", "password": "newpass456"}
    ).status_code == 200
    assert client.post(
        "/api/auth/login", json={"username": "pwuser", "password": "oldpass123"}
    ).status_code == 401


def test_change_password_wrong_current(client: TestClient):
    token = _make_login(client, "pwuser2", "oldpass123")
    r = client.post(
        "/api/auth/change-password",
        json={"current_password": "WRONG", "new_password": "newpass456"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400


def test_change_password_same_as_current(client: TestClient):
    token = _make_login(client, "pwuser3", "oldpass123")
    r = client.post(
        "/api/auth/change-password",
        json={"current_password": "oldpass123", "new_password": "oldpass123"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400


def test_change_password_too_short(client: TestClient):
    token = _make_login(client, "pwuser4", "oldpass123")
    r = client.post(
        "/api/auth/change-password",
        json={"current_password": "oldpass123", "new_password": "short"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422


def test_change_password_unauthenticated(client: TestClient):
    r = client.post(
        "/api/auth/change-password",
        json={"current_password": "x", "new_password": "newpass456"},
    )
    assert r.status_code == 401
