"""Pydantic models for API requests and responses.

NOTE: Genre prediction fields are currently commented out/paused as we focus on BPM analysis only.
The classes and types remain here for future use,
but active responses will focus on BPM values for individual or bulk (playlist) analysis.
"""

from typing import Literal, list

from pydantic import BaseModel, Field

# -- Genre prediction classes are NOT in current use, but preserved for future --
# class GenrePrediction(BaseModel):
#     """Genre label and confidence score."""
#     label: str
#     score: float

# class PredictionResult(BaseModel):
#     """Complete prediction result for an audio file."""
#     top_k: list[GenrePrediction] = Field(..., description="Top-k genre predictions")
#     bpm: float | None = Field(None, description="Estimated tempo in BPM")
#     # per_window: List[List[GenrePrediction]] = Field(..., description="Per-window predictions")

# class PredictionResponse(BaseModel):
#     """Response payload for prediction endpoints (genres, bpm, etc)."""
#     source: Literal["file", "spotify"] = "file"
#     filename: str | None = None
#     top_k: list[GenrePrediction]
#     bpm: float | None = None
#     # per_window: List[List[GenrePrediction]]

# -- Active response schemas for BPM-only analysis. --


class BPMResult(BaseModel):
    """BPM analysis result for a single song."""

    filename: str
    bpm: float | None = Field(
        None,
        description="Estimated tempo in BPM (beats per minute). May be None if tempo could not be analyzed.",
    )


class BPMBulkResponse(BaseModel):
    """Response schema for multiple (playlist) BPM analyses."""

    source: Literal["file", "playlist"] = "file"
    results: list[BPMResult] = Field(
        ..., description="List of BPM analysis results for each submitted file or item."
    )
