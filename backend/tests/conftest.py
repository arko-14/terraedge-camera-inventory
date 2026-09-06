"""Test configuration.

The suite runs against a throwaway SQLite file so `pytest` needs no Docker,
no Postgres and no network. The schema is portable by design (no Postgres-only
types), and SQLite foreign keys are switched on in app/database.py, so the
composite "beat must belong to range" constraint is genuinely exercised here.

Environment variables are set before any app module is imported, because the
engine and settings are built at import time.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

TEST_DB_PATH = Path(tempfile.gettempdir()) / "terraedge_test.db"

os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"
os.environ["JWT_SECRET"] = "test-secret-not-used-anywhere-real-0123456789"
os.environ["COOKIE_SECURE"] = "false"
os.environ["COOKIE_SAMESITE"] = "lax"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config import settings  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Beat, Range, User, UserRole  # noqa: E402
from app.security import hash_password  # noqa: E402

ADMIN_EMAIL = "admin@similipal.test"
CHAHALA_EMAIL = "chahala@similipal.test"
NAWANA_EMAIL = "nawana@similipal.test"
PASSWORD = "demo-password-123"

# Argon2 is deliberately slow. Hash once for the whole session and reuse.
_PASSWORD_HASH = hash_password(PASSWORD)


@pytest.fixture(autouse=True)
def fresh_database():
    """Every test starts from an empty, freshly migrated schema."""
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def reserve(db):
    """Two ranges, two beats each, one admin and one user per range."""
    chahala = Range(name="Chahala Range")
    nawana = Range(name="Nawana Range")
    db.add_all([chahala, nawana])
    db.flush()

    beats = {
        "bakua": Beat(range_id=chahala.id, name="Bakua Beat"),
        "jenabil": Beat(range_id=chahala.id, name="Jenabil Beat"),
        "barehipani": Beat(range_id=nawana.id, name="Barehipani Beat"),
        "joranda": Beat(range_id=nawana.id, name="Joranda Beat"),
    }
    db.add_all(list(beats.values()))

    db.add_all(
        [
            User(
                email=ADMIN_EMAIL,
                full_name="Reserve Administrator",
                password_hash=_PASSWORD_HASH,
                role=UserRole.RESERVE_ADMIN,
                range_id=None,
            ),
            User(
                email=CHAHALA_EMAIL,
                full_name="Chahala Range Officer",
                password_hash=_PASSWORD_HASH,
                role=UserRole.RANGE_USER,
                range_id=chahala.id,
            ),
            User(
                email=NAWANA_EMAIL,
                full_name="Nawana Range Officer",
                password_hash=_PASSWORD_HASH,
                role=UserRole.RANGE_USER,
                range_id=nawana.id,
            ),
        ]
    )
    db.commit()

    return {
        "chahala": chahala.id,
        "nawana": nawana.id,
        "bakua": beats["bakua"].id,
        "jenabil": beats["jenabil"].id,
        "barehipani": beats["barehipani"].id,
        "joranda": beats["joranda"].id,
    }


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


class ApiClient:
    """A signed-in API client.

    Defaults to the `Authorization: Bearer` path, which is exactly how a
    reviewer would poke the API with curl - so the authorisation tests below
    prove the backend enforces its rules rather than the UI hiding buttons.
    """

    def __init__(self, client: TestClient, email: str, password: str = PASSWORD):
        response = client.post("/api/auth/login", json={"email": email, "password": password})
        assert response.status_code == 200, response.text
        self._client = client
        self.token = response.json()["access_token"]
        self.user = response.json()["user"]
        self.csrf = client.cookies.get(settings.csrf_cookie_name)

    def _headers(self, extra: dict | None = None) -> dict:
        headers = {"Authorization": f"Bearer {self.token}"}
        headers.update(extra or {})
        return headers

    def get(self, url, **kw):
        return self._client.get(url, headers=self._headers(kw.pop("headers", None)), **kw)

    def post(self, url, **kw):
        return self._client.post(url, headers=self._headers(kw.pop("headers", None)), **kw)

    def patch(self, url, **kw):
        return self._client.patch(url, headers=self._headers(kw.pop("headers", None)), **kw)


@pytest.fixture
def admin(client, reserve):
    return ApiClient(client, ADMIN_EMAIL)


@pytest.fixture
def chahala_user(client, reserve):
    return ApiClient(client, CHAHALA_EMAIL)


@pytest.fixture
def nawana_user(client, reserve):
    return ApiClient(client, NAWANA_EMAIL)


def register(api: ApiClient, serial: str, **fields):
    response = api.post("/api/cameras", json={"serial_number": serial, **fields})
    assert response.status_code == 201, response.text
    return response.json()
