"""Health endpoint tests."""

import pytest
from fastapi.testclient import TestClient

from backend.app.app import app


@pytest.fixture()
def client() -> TestClient:
    """Return a TestClient that exercises the full application lifespan."""
    with TestClient(app) as c:
        yield c


def test_healthz(client: TestClient) -> None:
    """Health endpoint returns static service status."""
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "version": "0.1.0"}


def test_readyz(client: TestClient) -> None:
    """Readiness endpoint reports application state."""
    r = client.get("/readyz")
    assert r.status_code == 200
    resp = r.json()
    assert resp["status"] is True
    assert isinstance(resp["model_loaded"], bool)
