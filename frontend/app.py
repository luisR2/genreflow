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
    from collections.abc import AsyncGenerator

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
