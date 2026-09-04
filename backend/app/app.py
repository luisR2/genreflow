"""FastAPI application entrypoint for the GenreFlow service."""

import logging
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
