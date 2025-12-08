"""FastAPI application entrypoint for the GenreFlow service."""

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.app.logging_utils import configure_logging
from backend.app.routes_file import _predictor
from backend.app.routes_file import router as file_router


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

# CORS configuration - adjust origins for production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: restrict this in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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


# Include routers
app.include_router(file_router)
