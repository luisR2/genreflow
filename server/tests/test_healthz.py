

from fastapi.testclient import TestClient
from server.app import app

client = TestClient(app)

def test_healthz():
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}

def test_readyz():
    r = client.get("/readyz")
    assert r.status_code == 200
    assert r.json() == {"status": True}