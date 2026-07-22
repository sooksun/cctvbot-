import os

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["API_SECRET_KEY"] = "test-secret-key-at-least-32-characters"
os.environ["SYSTEM_API_TOKEN"] = "test-system-token"
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = "admin123!"

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from app.main import app

    with TestClient(app) as c:
        yield c
