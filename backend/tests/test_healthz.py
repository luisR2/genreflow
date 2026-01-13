"""Health endpoint tests."""

from fastapi.testclient import TestClient

from backend.app.app import app

client = TestClient(app)


def test_healthz() -> None:
    """Health endpoint returns static service status."""
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "version": "0.1.0"}


def test_readyz() -> None:
    """Readiness endpoint reports application state."""
    r = client.get("/readyz")
    assert r.status_code == 200
    # model_loaded depends on _predictor, which may be None in test context
    resp = r.json()
    assert resp["status"] is True
    assert isinstance(resp["model_loaded"], bool)
