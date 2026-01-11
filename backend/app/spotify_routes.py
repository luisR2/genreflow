"""Routes for Spotify track metadata and audio feature enrichment."""

from __future__ import annotations

import logging
import os
import re
from typing import TYPE_CHECKING, Any, TypeVar
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, model_validator

from backend.app.schemas import SpotifyAnalysisSummary, SpotifyAudioFeatures, SpotifyTrackInfo
from backend.app.spotify_client import MockSpotifyClient, SpotifyAPIError, SpotifyClient

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/spotify", tags=["spotify"])

TRACK_URI_PATTERN = re.compile(r"^spotify:track:(?P<id>[A-Za-z0-9]{22})$")


class SpotifyTrackRequest(BaseModel):
    """Request payload for Spotify track metadata."""

    track_id: str | None = Field(None, description="Spotify track ID")
    track_url: str | None = Field(None, description="Spotify track URL or URI")

    @model_validator(mode="after")
    def validate_track_input(self) -> SpotifyTrackRequest:
        """Ensure the request includes a track identifier."""
        if not self.track_id and not self.track_url:
            raise ValueError("Provide either track_id or track_url")
        return self


def _extract_track_id(track_input: str) -> str | None:
    if match := TRACK_URI_PATTERN.match(track_input):
        return match.group("id")

    parsed = urlparse(track_input)
    if parsed.netloc.endswith("spotify.com"):
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) >= 2 and parts[0] == "track":
            track_id = parts[1]
            if len(track_id) == 22:
                return track_id

    if len(track_input) == 22:
        return track_input
    return None


def _get_spotify_client() -> SpotifyClient:
    if _use_mock_spotify():
        return MockSpotifyClient()
    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Spotify client credentials are not configured",
        )
    return SpotifyClient(client_id=client_id, client_secret=client_secret)


def _use_mock_spotify() -> bool:
    return os.getenv("SPOTIFY_USE_MOCK", "").strip().lower() in {"1", "true", "yes", "on"}


def _build_audio_features(features: dict[str, Any]) -> SpotifyAudioFeatures:
    key = features.get("key")
    mode = features.get("mode")
    return SpotifyAudioFeatures(
        tempo=features.get("tempo"),
        key=key,
        key_name=SpotifyAudioFeatures.key_name_from_value(key),
        mode=mode,
        mode_name=SpotifyAudioFeatures.mode_name_from_value(mode),
        time_signature=features.get("time_signature"),
        energy=features.get("energy"),
        danceability=features.get("danceability"),
        valence=features.get("valence"),
        acousticness=features.get("acousticness"),
        instrumentalness=features.get("instrumentalness"),
        liveness=features.get("liveness"),
        loudness=features.get("loudness"),
        speechiness=features.get("speechiness"),
    )


def _build_analysis_summary(analysis: dict[str, Any]) -> SpotifyAnalysisSummary | None:
    track_summary = analysis.get("track")
    if not isinstance(track_summary, dict):
        return None
    key = track_summary.get("key")
    mode = track_summary.get("mode")
    return SpotifyAnalysisSummary(
        tempo=track_summary.get("tempo"),
        key=key,
        key_name=SpotifyAudioFeatures.key_name_from_value(key),
        mode=mode,
        mode_name=SpotifyAudioFeatures.mode_name_from_value(mode),
        time_signature=track_summary.get("time_signature"),
        loudness=track_summary.get("loudness"),
        duration=track_summary.get("duration"),
    )


@router.post(
    "/track-info",
    response_model=SpotifyTrackInfo,
    status_code=status.HTTP_200_OK,
    summary="Fetch Spotify track metadata and audio features",
)
async def spotify_track_info(payload: SpotifyTrackRequest) -> SpotifyTrackInfo:
    """Return Spotify track metadata, audio features, and genres."""
    track_input = payload.track_id or payload.track_url
    track_id = _extract_track_id(track_input or "")
    if not track_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Spotify track input")

    client = _get_spotify_client()
    try:
        track = await _fetch_track(client, track_id)
        audio_features = await _fetch_audio_features(client, track_id)
        audio_analysis = await _fetch_audio_analysis(client, track_id)
        artists = await _fetch_artists(client, track)
    except SpotifyAPIError as exc:
        logger.error("Spotify API error for track %s: %s", track_id, exc)
        status_code = status.HTTP_502_BAD_GATEWAY
        if exc.status_code == 404:
            status_code = status.HTTP_404_NOT_FOUND
        raise HTTPException(status_code=status_code, detail=str(exc))

    genre_list: list[str] = []
    for artist in artists:
        genre_list.extend(artist.get("genres", []))

    unique_genres = sorted(set(genre_list))

    return SpotifyTrackInfo(
        track_id=track_id,
        name=track.get("name", ""),
        artists=[artist.get("name", "") for artist in track.get("artists", [])],
        artist_ids=[artist.get("id", "") for artist in track.get("artists", [])],
        album=track.get("album", {}).get("name"),
        release_date=track.get("album", {}).get("release_date"),
        duration_ms=track.get("duration_ms"),
        explicit=track.get("explicit"),
        popularity=track.get("popularity"),
        preview_url=track.get("preview_url"),
        external_url=track.get("external_urls", {}).get("spotify"),
        genres=unique_genres,
        audio_features=_build_audio_features(audio_features),
        analysis_summary=_build_analysis_summary(audio_analysis),
    )


async def _fetch_track(client: SpotifyClient, track_id: str) -> dict[str, Any]:
    return await _run_blocking(client.get_track, track_id)


async def _fetch_audio_features(client: SpotifyClient, track_id: str) -> dict[str, Any]:
    return await _run_blocking(client.get_audio_features, track_id)


async def _fetch_audio_analysis(client: SpotifyClient, track_id: str) -> dict[str, Any]:
    return await _run_blocking(client.get_audio_analysis, track_id)


async def _fetch_artists(client: SpotifyClient, track: dict[str, Any]) -> list[dict[str, Any]]:
    artist_ids = [artist.get("id") for artist in track.get("artists", []) if artist.get("id")]
    if not artist_ids:
        return []
    data = await _run_blocking(client.get_artists, artist_ids)
    artists = data.get("artists")
    if isinstance(artists, list):
        return artists
    return []


T = TypeVar("T")


async def _run_blocking(func: Callable[..., T], *args: object) -> T:
    import asyncio

    return await asyncio.to_thread(func, *args)
