"""Pydantic models for API requests and responses.

NOTE: Genre prediction fields are currently commented out/paused as we focus on BPM analysis only.
The classes and types remain here for future use,
but active responses will focus on BPM values for individual or bulk (playlist) analysis.
"""

from typing import Literal

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
    analysis_time: float = Field(..., description="Time taken to analyze the audio in seconds.")


class BPMBulkResponse(BaseModel):
    """Response schema for multiple (playlist) BPM analyses."""

    source: Literal["file", "playlist"] = "file"
    results: list[BPMResult] = Field(
        ..., description="List of BPM analysis results for each submitted file or item."
    )
    analysis_time: float = Field(..., description="Time taken to analyze the audio in seconds.")


class SpotifyAudioFeatures(BaseModel):
    """Spotify audio feature analysis for a track."""

    tempo: float | None = Field(None, description="Estimated tempo in BPM from Spotify.")
    key: int | None = Field(None, description="Key index from Spotify (0=C, 1=C#, ... 11=B).")
    key_name: str | None = Field(None, description="Human-readable musical key.")
    mode: int | None = Field(None, description="Mode from Spotify (1=major, 0=minor).")
    mode_name: str | None = Field(None, description="Human-readable mode name.")
    time_signature: int | None = Field(None, description="Estimated time signature from Spotify.")
    energy: float | None = Field(None, description="Energy metric from Spotify.")
    danceability: float | None = Field(None, description="Danceability metric from Spotify.")
    valence: float | None = Field(None, description="Valence metric from Spotify.")
    acousticness: float | None = Field(None, description="Acousticness metric from Spotify.")
    instrumentalness: float | None = Field(None, description="Instrumentalness metric from Spotify.")
    liveness: float | None = Field(None, description="Liveness metric from Spotify.")
    loudness: float | None = Field(None, description="Loudness in dB from Spotify.")
    speechiness: float | None = Field(None, description="Speechiness metric from Spotify.")

    @staticmethod
    def key_name_from_value(value: int | None) -> str | None:
        """Translate Spotify key index into a musical key name."""
        if value is None:
            return None
        keys = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
        if 0 <= value < len(keys):
            return keys[value]
        return None

    @staticmethod
    def mode_name_from_value(value: int | None) -> str | None:
        """Translate Spotify mode integer into a name."""
        if value is None:
            return None
        if value == 1:
            return "major"
        if value == 0:
            return "minor"
        return None


class SpotifyAnalysisSummary(BaseModel):
    """Summary of Spotify audio analysis metadata."""

    tempo: float | None = Field(None, description="Tempo from Spotify audio analysis.")
    key: int | None = Field(None, description="Key index from Spotify audio analysis.")
    key_name: str | None = Field(None, description="Human-readable musical key.")
    mode: int | None = Field(None, description="Mode index from Spotify audio analysis.")
    mode_name: str | None = Field(None, description="Human-readable mode name.")
    time_signature: int | None = Field(None, description="Time signature from Spotify analysis.")
    loudness: float | None = Field(None, description="Track loudness from Spotify analysis.")
    duration: float | None = Field(None, description="Track duration from Spotify analysis.")


class SpotifyTrackInfo(BaseModel):
    """Response payload containing Spotify track details and audio features."""

    track_id: str
    name: str
    artists: list[str] = Field(default_factory=list)
    artist_ids: list[str] = Field(default_factory=list)
    album: str | None = None
    release_date: str | None = None
    duration_ms: int | None = None
    explicit: bool | None = None
    popularity: int | None = None
    preview_url: str | None = None
    external_url: str | None = None
    genres: list[str] = Field(default_factory=list)
    audio_features: SpotifyAudioFeatures
    analysis_summary: SpotifyAnalysisSummary | None = None
