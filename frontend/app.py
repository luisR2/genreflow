"""Minimal FastAPI-powered UI service for GenreFlow uploads.

The UI also proxies analysis requests to the backend. The browser therefore only
ever talks to this service's own origin, which keeps the backend on a ClusterIP
with no ingress of its own and removes the need for CORS.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Awaitable, Callable

logger = logging.getLogger(__name__)

# Backend base URL. In-cluster this is the backend Service's DNS name; the
# backend is never reachable from outside, only through the proxy below.
API_BASE_URL = os.getenv("GENREFLOW_API_BASE_URL", "http://localhost:8080").rstrip("/")

# Upstream request timeout in seconds. Analysis is CPU-bound and slower on a Pi
# than on a laptop, so this is generous; note that a CDN or tunnel in front of
# this service may impose its own, shorter, ceiling.
UPSTREAM_TIMEOUT = float(os.getenv("GENREFLOW_UPSTREAM_TIMEOUT", "120"))

# Backend paths the proxy is willing to forward to, as an explicit allowlist so
# this cannot be used as a general-purpose proxy into the cluster.
PROXYABLE_PREDICT_PATHS = frozenset({"file", "files"})

# Content Security Policy, written as an allowlist over a `default-src 'none'`
# baseline so anything not listed is refused. Kept in step with what the page
# actually loads:
#   script-src  -- /static/app.js only; the page has no inline script
#   style-src   -- /static/styles.css
#   font-src    -- /static/fonts/*.woff2, self-hosted rather than pulled from
#                  Google Fonts, which is what lets both of these stay 'self'
#   connect-src -- the uploads, which go to this service's own /api/predict/*
#
# Every directive is 'self' or 'none': the page loads nothing from a third
# party, so nothing third-party needs naming here. Keep it that way -- adding
# an external asset means widening this, and leaking visitor IPs to whoever
# serves it.
CONTENT_SECURITY_POLICY = "; ".join(
    (
        "default-src 'none'",
        "script-src 'self'",
        "style-src 'self'",
        "font-src 'self'",
        "img-src 'self' data:",
        "connect-src 'self'",
        "form-action 'none'",
        "frame-ancestors 'none'",
        "base-uri 'none'",
    )
)

# Applied to every response, including the JSON the proxy relays back, where
# `nosniff` matters most. No HSTS: TLS terminates at Cloudflare, so the origin
# only ever speaks plain HTTP and would be asserting something it cannot honour.
SECURITY_HEADERS = {
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    # Redundant with frame-ancestors above, for browsers that honour only one.
    "X-Frame-Options": "DENY",
    # The UI reads local files the user picks; it needs no device access.
    "Permissions-Policy": "accelerometer=(), camera=(), geolocation=(), microphone=(), usb=()",
}

FRONTEND_DIR = Path(__file__).parent
STATIC_DIR = FRONTEND_DIR / "static"
INDEX_FILE = FRONTEND_DIR / "templates/index.html"


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
    """Hold a pooled HTTP client for the lifetime of the app."""
    async with httpx.AsyncClient(timeout=UPSTREAM_TIMEOUT) as client:
        application.state.client = client
        logger.info("Frontend proxying analysis requests to %s", API_BASE_URL)
        yield


app = FastAPI(
    title="GenreFlow UI",
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)

@app.middleware("http")
async def add_security_headers(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Attach the security headers to every response this service returns.

    Args:
        request: The incoming request.
        call_next: The next handler in the middleware chain.

    Returns:
        The downstream response, with the security headers set.
    """
    response = await call_next(request)
    response.headers.update(SECURITY_HEADERS)
    return response


# Serve static assets (JS/CSS)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", response_class=FileResponse)
async def index() -> FileResponse:
    """Return the SPA shell."""
    return FileResponse(INDEX_FILE)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    """Simple liveness endpoint for the UI service."""
    return {"status": "ok"}


@app.post("/api/predict/{endpoint}")
async def proxy_predict(endpoint: str, request: Request) -> Response:
    """Forward an upload to the backend and relay its response verbatim.

    The request body is streamed upstream rather than buffered, so a large upload
    does not have to be held in this pod's memory on its way through.

    Args:
        endpoint: Backend predict endpoint to target; must be in the allowlist.
        request: The incoming upload request.

    Returns:
        The backend's response, or a gateway error if it could not be reached.
    """
    if endpoint not in PROXYABLE_PREDICT_PATHS:
        return JSONResponse(status_code=404, content={"detail": "Unknown endpoint."})

    client: httpx.AsyncClient = request.app.state.client
    content_type = request.headers.get("content-type")
    headers = {"content-type": content_type} if content_type else {}

    try:
        upstream = await client.post(
            f"{API_BASE_URL}/predict/{endpoint}",
            content=request.stream(),
            headers=headers,
        )
    except httpx.TimeoutException:
        logger.warning("Upstream timed out after %.0fs on /predict/%s", UPSTREAM_TIMEOUT, endpoint)
        return JSONResponse(
            status_code=504,
            content={"detail": "Analysis timed out. Try fewer or shorter files."},
        )
    except httpx.RequestError:
        logger.exception("Upstream request to /predict/%s failed", endpoint)
        return JSONResponse(
            status_code=502,
            content={"detail": "Analysis service is unavailable. Please try again later."},
        )

    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type"),
    )
