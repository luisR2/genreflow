"""Tests for the frontend service's /api proxy to the backend.

These cover `frontend/app.py` rather than the backend package. They live here
because `make test` collects from `backend/`, so this is where CI will run them.

The upstream backend is faked with an httpx MockTransport, so nothing here
depends on a running backend.
"""

import importlib.util
import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

FRONTEND_APP = Path(__file__).resolve().parents[2] / "frontend" / "app.py"


def _load_frontend_app():
    """Import frontend/app.py by path, since `frontend` is not on sys.path."""
    spec = importlib.util.spec_from_file_location("genreflow_frontend_app", FRONTEND_APP)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


frontend = _load_frontend_app()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def proxied():
    """Yield (client, record) with the upstream backend mocked.

    `record` accumulates the requests the proxy actually forwarded, so tests can
    assert on what reached the backend. Set `record["handler"]` to override the
    canned response.
    """
    record: dict = {"requests": [], "handler": None}

    def handler(request: httpx.Request) -> httpx.Response:
        record["requests"].append(request)
        if record["handler"] is not None:
            return record["handler"](request)
        return httpx.Response(200, json={"results": [], "analysis_time": 0.0})

    with TestClient(frontend.app) as client:
        client.app.state.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        yield client, record


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_proxy_forwards_to_backend_and_relays_response(proxied):
    """A bulk upload reaches the backend and its response comes back unchanged."""
    client, record = proxied
    r = client.post("/api/predict/files", files=[("files", ("a.wav", b"RIFFfake", "audio/wav"))])

    assert r.status_code == 200
    assert r.json() == {"results": [], "analysis_time": 0.0}
    assert len(record["requests"]) == 1
    assert record["requests"][0].url.path == "/predict/files"


def test_proxy_forwards_single_file_endpoint(proxied):
    """The single-file endpoint is proxied too."""
    client, record = proxied
    client.post("/api/predict/file", files={"file": ("a.wav", b"RIFFfake", "audio/wav")})
    assert record["requests"][0].url.path == "/predict/file"


def test_proxy_forwards_request_body_and_content_type(proxied):
    """The upload body and its multipart content type reach the backend intact."""
    client, record = proxied
    client.post("/api/predict/files", files=[("files", ("a.wav", b"DISTINCTIVE", "audio/wav"))])

    sent = record["requests"][0]
    assert b"DISTINCTIVE" in sent.content
    assert sent.headers["content-type"].startswith("multipart/form-data")


# ---------------------------------------------------------------------------
# Error relaying
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status_code", [400, 413, 415, 500])
def test_proxy_relays_backend_error_status_and_detail(proxied, status_code):
    """Backend rejections reach the browser with their status and message intact.

    Without this the UI cannot tell "file too large" from "not audio".
    """
    client, record = proxied
    record["handler"] = lambda req: httpx.Response(status_code, json={"detail": "nope"})

    r = client.post("/api/predict/files", files=[("files", ("a.wav", b"x", "audio/wav"))])
    assert r.status_code == status_code
    assert r.json()["detail"] == "nope"


def test_proxy_returns_504_when_backend_times_out(proxied):
    """A slow backend surfaces as a gateway timeout, not a 500."""
    client, record = proxied

    def timeout(request):
        raise httpx.ReadTimeout("too slow", request=request)

    record["handler"] = timeout
    r = client.post("/api/predict/files", files=[("files", ("a.wav", b"x", "audio/wav"))])
    assert r.status_code == 504
    assert "timed out" in r.json()["detail"].lower()


def test_proxy_returns_502_when_backend_unreachable(proxied):
    """An unreachable backend surfaces as a bad gateway."""
    client, record = proxied

    def refuse(request):
        raise httpx.ConnectError("refused", request=request)

    record["handler"] = refuse
    r = client.post("/api/predict/files", files=[("files", ("a.wav", b"x", "audio/wav"))])
    assert r.status_code == 502


def test_proxy_error_does_not_leak_upstream_url(proxied):
    """Gateway errors must not disclose the internal backend address."""
    client, record = proxied

    def refuse(request):
        raise httpx.ConnectError("refused", request=request)

    record["handler"] = refuse
    r = client.post("/api/predict/files", files=[("files", ("a.wav", b"x", "audio/wav"))])
    assert "svc.cluster.local" not in r.text
    assert "http://" not in r.text


# ---------------------------------------------------------------------------
# The proxy is not a general-purpose tunnel
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("endpoint", ["healthz", "readyz", "docs", "openapi.json", "..%2Fhealthz"])
def test_proxy_rejects_non_allowlisted_endpoints(proxied, endpoint):
    """Only the two predict endpoints are proxyable.

    Guards against the proxy becoming a way to reach arbitrary backend paths, or
    anything else the frontend pod can route to inside the cluster.
    """
    client, record = proxied
    r = client.post(f"/api/predict/{endpoint}", files=[("files", ("a.wav", b"x", "audio/wav"))])

    assert r.status_code == 404
    assert record["requests"] == [], "request must not reach the backend"


# ---------------------------------------------------------------------------
# Static surface
# ---------------------------------------------------------------------------


def test_index_is_served(proxied):
    """The SPA shell is served at the root."""
    client, _ = proxied
    assert client.get("/").status_code == 200


def test_config_endpoint_is_gone(proxied):
    """/config.json existed only to hand the browser a backend URL."""
    client, _ = proxied
    assert client.get("/config.json").status_code == 404


def test_frontend_exposes_no_api_docs(proxied):
    """The UI service publishes no OpenAPI surface."""
    client, _ = proxied
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_browser_bundle_uses_same_origin_api(proxied):
    """app.js must call the same-origin proxy, never an absolute backend URL."""
    client, _ = proxied
    js = client.get("/static/app.js").text
    assert "/api/predict/file" in js
    assert "apiBaseUrl" not in js


def test_browser_bundle_uploads_one_file_per_request(proxied):
    """The UI must not use the bulk endpoint.

    One request per file is what keeps an upload inside the body-size and
    origin-timeout limits a tunnel imposes, however many files are queued. A
    regression here would not fail any backend test, so it is asserted on the
    shipped bundle.
    """
    client, _ = proxied
    js = client.get("/static/app.js").text
    assert '"/api/predict/file"' in js
    assert "/api/predict/files" not in js
