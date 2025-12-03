"""Minimal FastAPI-powered UI service for GenreFlow uploads."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# Frontend config
API_BASE_URL = os.getenv("GENREFLOW_API_BASE_URL", "http://localhost:8080").rstrip("/")
FRONTEND_DIR = Path(__file__).parent
STATIC_DIR = FRONTEND_DIR / "static"
INDEX_FILE = FRONTEND_DIR / "index.html"

app = FastAPI(
    title="GenreFlow UI",
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

# Serve static assets (JS/CSS)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", response_class=FileResponse)
async def index() -> FileResponse:
    """Return the SPA shell."""
    return FileResponse(INDEX_FILE)


@app.get("/config.json")
async def config() -> dict[str, Any]:
    """Expose runtime config consumed by the frontend JS."""
    return {"apiBaseUrl": API_BASE_URL}


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    """Simple liveness endpoint for the UI service."""
    return {"status": "ok"}
