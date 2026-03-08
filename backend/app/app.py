"""FastAPI application entrypoint for the GenreFlow service."""

import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app.logging_utils import configure_logging
from backend.app.predict import Predictor
from backend.app.schemas import HealthResponse, ReadinessResponse

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application startup and shutdown lifecycle."""
    configure_logging()
    application.state.predictor = Predictor.load()
    yield
    application.state.predictor = None


app = FastAPI(
    title="GenreFlow",
    version="0.1.0",
    description="Music genre classification API using deep learning",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
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
async def readyz(request: Request) -> ReadinessResponse:
    """Report service readiness state."""
    predictor = getattr(request.app.state, "predictor", None)
    return ReadinessResponse(status=True, model_loaded=predictor is not None)


# Exception handlers
@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle all unhandled exceptions without leaking internal details to the client."""
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An unexpected error occurred. Please try again later."},
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


from backend.app.routes_file import router as file_router  # noqa: E402

# Include routers
app.include_router(file_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_get_allowed_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
