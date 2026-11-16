"""Security header and API-docs exposure tests (go-live plan item 1.5)."""

import importlib
import re
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.tests.test_frontend_proxy import _load_frontend_app

frontend = _load_frontend_app()

# `from backend.app import app` hands back the FastAPI instance rather than the
# module, because `backend.app.app` the object shadows `backend.app.app` the
# module on the package. import_module is unambiguous.
backend_app_module = importlib.import_module("backend.app.app")

REPO_ROOT = Path(__file__).resolve().parents[2]
STYLES_CSS = REPO_ROOT / "frontend" / "static" / "styles.css"
INDEX_HTML = REPO_ROOT / "frontend" / "templates" / "index.html"

EXPECTED_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
}


@pytest.fixture()
def client():
    """Yield a frontend TestClient with the upstream backend mocked."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"filename": "x.wav", "bpm": 128.0, "analysis_time": 0.1})

    with TestClient(frontend.app) as c:
        c.app.state.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        yield c


def _without_comments(css: str) -> str:
    """Strip /* ... */ comments, so prose about CSS is not mistaken for CSS."""
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


# ---------------------------------------------------------------------------
# Headers are on every response
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/", "/healthz", "/static/app.js", "/static/styles.css"])
def test_security_headers_present(client: TestClient, path: str) -> None:
    res = client.get(path)
    assert res.status_code == 200
    for header, value in EXPECTED_HEADERS.items():
        assert res.headers[header] == value
    assert "default-src 'none'" in res.headers["Content-Security-Policy"]


def test_security_headers_on_proxied_json(client: TestClient) -> None:
    """nosniff matters most on the JSON the proxy relays back."""
    res = client.post("/api/predict/file", files={"file": ("x.wav", b"RIFF", "audio/wav")})
    assert res.status_code == 200
    assert res.headers["X-Content-Type-Options"] == "nosniff"


def test_security_headers_on_error_responses(client: TestClient) -> None:
    """A rejected path must not be a way to get a response without the headers."""
    res = client.post("/api/predict/not-allowed", files={"file": ("x.wav", b"RIFF", "audio/wav")})
    assert res.status_code == 404
    assert res.headers["X-Frame-Options"] == "DENY"
    assert "default-src 'none'" in res.headers["Content-Security-Policy"]


# ---------------------------------------------------------------------------
# The CSP has to match what the page actually loads
# ---------------------------------------------------------------------------


def test_csp_directives(client: TestClient) -> None:
    csp = client.get("/").headers["Content-Security-Policy"]
    directives = dict((part.split(" ", 1) + [""])[:2] for part in (p.strip() for p in csp.split(";")) if part)
    assert directives["default-src"] == "'none'"
    assert directives["script-src"] == "'self'"
    assert directives["connect-src"] == "'self'"
    assert directives["frame-ancestors"] == "'none'"
    assert directives["base-uri"] == "'none'"
    assert directives["form-action"] == "'none'"


def test_page_has_no_inline_script_or_style() -> None:
    """script-src 'self' holds only while nothing on the page is inline."""
    html = INDEX_HTML.read_text()
    assert not re.search(r"<script(?![^>]*\bsrc=)", html)
    assert "<style" not in html
    assert not re.search(r"\son[a-z]+\s*=", html)


def test_no_external_assets_and_no_external_csp_hosts() -> None:
    """The page loads nothing third-party, so the CSP must name nothing third-party.

    These move together: adding an external asset means widening the policy and
    leaking visitor IPs to whoever serves it. This fails on either half.
    """
    css = _without_comments(STYLES_CSS.read_text())
    assert "@import" not in css
    assert "fonts.googleapis.com" not in css
    assert "fonts.gstatic.com" not in css

    html = INDEX_HTML.read_text()
    assert not re.search(r"(?:href|src)\s*=\s*[\"\']https?://", html)

    assert "http://" not in frontend.CONTENT_SECURITY_POLICY
    assert "https://" not in frontend.CONTENT_SECURITY_POLICY


def test_fonts_are_served_from_this_origin() -> None:
    """Every @font-face src must be a local path under /static."""
    css = _without_comments(STYLES_CSS.read_text())
    srcs = re.findall(r"src:\s*url\(\"([^\"]+)\"\)", css)
    assert srcs, "expected self-hosted @font-face rules"
    assert all(s.startswith("/static/fonts/") for s in srcs)
    for s in srcs:
        assert (REPO_ROOT / "frontend" / s.lstrip("/")).is_file(), f"missing font file: {s}"


def test_font_files_are_actually_woff2() -> None:
    """Guard against committing an HTML error page under a .woff2 name."""
    for path in (REPO_ROOT / "frontend" / "static" / "fonts").glob("*.woff2"):
        assert path.read_bytes()[:4] == b"wOF2", f"{path.name} is not a woff2 file"


def test_fonts_are_reachable_over_http(client: TestClient) -> None:
    css = _without_comments(STYLES_CSS.read_text())
    for src in set(re.findall(r"src:\s*url\(\"([^\"]+)\"\)", css)):
        res = client.get(src)
        assert res.status_code == 200
        assert res.content[:4] == b"wOF2"


# ---------------------------------------------------------------------------
# Backend API docs are opt-in
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_backend_docs_disabled_by_default(monkeypatch, path: str) -> None:
    monkeypatch.delenv(backend_app_module.DOCS_ENV_VAR, raising=False)
    module = importlib.reload(backend_app_module)
    with TestClient(module.app) as c:
        assert c.get(path).status_code == 404


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_backend_docs_enabled_by_env(monkeypatch, path: str) -> None:
    monkeypatch.setenv(backend_app_module.DOCS_ENV_VAR, "1")
    module = importlib.reload(backend_app_module)
    with TestClient(module.app) as c:
        assert c.get(path).status_code == 200


def test_backend_module_restored_for_other_tests(monkeypatch) -> None:
    """Reloading the module above must not leave the suite with a stale app."""
    monkeypatch.delenv(backend_app_module.DOCS_ENV_VAR, raising=False)
    module = importlib.reload(backend_app_module)
    assert module.app.openapi_url is None


def test_frontend_docs_stay_disabled(client: TestClient) -> None:
    """The UI never served a schema and must not start."""
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404
