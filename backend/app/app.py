"""FastAPI application entrypoint for the GenreFlow service."""

import logging
import os
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from backend.app.logging_utils import configure_logging
from backend.app.predict import Predictor
from backend.app.routes_file import reject_oversized_request
from backend.app.routes_file import router as file_router
from backend.app.schemas import HealthResponse, ReadinessResponse

logger = logging.getLogger(__name__)

# Set to a falsy value to skip the startup warm-up. On by default: the warm-up
# exists to keep librosa's ~12s JIT compilation off the first real request. Tests
# disable it, since they have no use for it and it would slow every fixture.
WARMUP_ENV_VAR = "GENREFLOW_WARMUP"
_FALSY = frozenset({"0", "false", "no", "off"})


def _warmup_enabled() -> bool:
    """Return whether the predictor should warm up during startup."""
    return os.getenv(WARMUP_ENV_VAR, "1").strip().lower() not in _FALSY


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application startup and shutdown lifecycle."""
    configure_logging()
    predictor = Predictor.load()

    # Warm up before publishing the predictor, so readiness is never reported
    # while the JIT cost is still outstanding. The server does not accept
    # requests until this context manager yields; the startup probe covers the
    # wait.
    if _warmup_enabled():
        await predictor.warm_up()
    else:
        logger.info("Predictor warm-up disabled via %s", WARMUP_ENV_VAR)

    application.state.predictor = predictor
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


@app.middleware("http")
async def limit_request_size(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Reject oversized uploads before the request body is parsed.

    Middleware runs ahead of route handlers and therefore ahead of Starlette's
    multipart parser, which spools every uploaded part to disk. Checking the
    declared size here means an oversized body is refused without being read.
    """
    try:
        reject_oversized_request(request.headers.get("content-length"))
    except HTTPException as exc:
        logger.warning(
            "Rejected %s %s: declared body exceeds the request size limit",
            request.method,
            request.url.path,
        )
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    return await call_next(request)


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


# Include routers
app.include_router(file_router)
