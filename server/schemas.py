"""Pydantic models for API requests and responses."""

from typing import Literal

from pydantic import BaseModel, Field


class GenrePrediction(BaseModel):
    """Genre label and confidence score."""

    label: str
    score: float


class PredictionResult(BaseModel):
    """Complete prediction result for an audio file."""

    top_k: list[GenrePrediction] = Field(..., description="Top-k genre predictions")
    bpm: float | None = Field(None, description="Estimated tempo in BPM")
    # per_window: List[List[GenrePrediction]] = Field(..., description="Per-window predictions")


class PredictionResponse(BaseModel):
    """Response payload for prediction endpoints."""

    source: Literal["file", "spotify"] = "file"
    filename: str | None = None
    top_k: list[GenrePrediction]
    bpm: float | None = None
    # per_window: List[List[GenrePrediction]]
