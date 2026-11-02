import os
import tempfile

# Must be set before importing the app: the engine is created at import time.
# Defaults to throwaway SQLite + in-memory cache; CI points these at real Postgres/Redis.
_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", f"sqlite:///{_tmp}/test.db")
os.environ["SECRET_KEY"] = "test-secret-key-that-is-at-least-32-bytes-long"
if os.environ.get("TEST_REDIS_URL"):
    os.environ["REDIS_URL"] = os.environ["TEST_REDIS_URL"]
else:
    os.environ.pop("REDIS_URL", None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.cache import get_cache  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def clean_state():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    get_cache().clear()
    yield


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def settings():
    return get_settings()


def register_and_login(client, email="a@example.com", password="password123"):
    client.post("/api/auth/register", json={"email": email, "password": password})
    token = client.post("/api/auth/login", json={"email": email, "password": password}).json()[
        "access_token"
    ]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth(client):
    return register_and_login(client)
