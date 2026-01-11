"""FastAPI application entrypoint for the GenreFlow service."""

import os

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.app.logging_utils import configure_logging
from backend.app.routes_file import _predictor
from backend.app.routes_file import router as file_router
from backend.app.spotify_routes import router as spotify_router


class HealthResponse(BaseModel):
    """Health check response payload."""

    status: str
    version: str


class ReadinessResponse(BaseModel):
    """Readiness check response payload."""

    status: bool
    model_loaded: bool


app = FastAPI(
    title="GenreFlow",
    version="0.1.0",
    description="Music genre classification API using deep learning",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)


@app.get(
    "/healthz",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    tags=["health"],
    summary="Health check endpoint",
)
async def healthz() -> HealthResponse:
    """Return service health metadata."""
    return HealthResponse(status="ok", version=app.version)


@app.get(
    "/readyz",
    response_model=ReadinessResponse,
    status_code=status.HTTP_200_OK,
    tags=["health"],
    summary="Readiness check endpoint",
)
async def readyz() -> ReadinessResponse:
    """Report service readiness state."""
    return ReadinessResponse(status=True, model_loaded=_predictor is not None)


@app.on_event("startup")
async def startup_event() -> None:
    """Initialize resources on startup."""
    configure_logging()


@app.on_event("shutdown")
async def shutdown_event() -> None:
    """Cleanup resources on shutdown."""
    # Add any cleanup code here
    pass


# Exception handlers
@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle all unhandled exceptions."""
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": f"Internal server error: {str(exc)}"},
    )


def _get_allowed_origins() -> list[str]:
    """Resolve allowed origins from env or fallback list."""
    env_origins = os.getenv("GENREFLOW_ALLOWED_ORIGINS")
    if env_origins:
        return [origin.strip() for origin in env_origins.split(",") if origin.strip()]
    return [
        "http://ui.genreflow.local",
        "http://genreflow.local",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    ]


# Include routers
app.include_router(file_router)
app.include_router(spotify_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_get_allowed_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
