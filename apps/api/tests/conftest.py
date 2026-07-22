import os

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["API_SECRET_KEY"] = "test-secret-key-at-least-32-characters"
os.environ["SYSTEM_API_TOKEN"] = "test-system-token"
