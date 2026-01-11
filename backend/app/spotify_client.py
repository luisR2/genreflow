"""Spotify API client for track metadata and audio features."""

from __future__ import annotations

import base64
import copy
import time
from dataclasses import dataclass
from typing import Any

import requests

SPOTIFY_API_BASE_URL = "https://api.spotify.com/v1"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"


@dataclass
class SpotifyAccessToken:
    """Cached access token data."""

    token: str
    expires_at: float


class SpotifyAPIError(RuntimeError):
    """Error raised when the Spotify API responds with an error."""

    def __init__(self, status_code: int, message: str) -> None:
        """Initialize the API error with a status code and message."""
        super().__init__(message)
        self.status_code = status_code


class SpotifyClient:
    """Client for interacting with the Spotify Web API using client credentials."""

    def __init__(self, client_id: str, client_secret: str) -> None:
        """Initialize the client with Spotify application credentials."""
        self._client_id = client_id
        self._client_secret = client_secret
        self._token: SpotifyAccessToken | None = None

    def _request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
        data: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        response = requests.request(
            method,
            url,
            timeout=15,
            headers=headers,
            params=params,
            data=data,
        )
        if response.status_code >= 400:
            message = response.text or response.reason
            raise SpotifyAPIError(response.status_code, message)
        return response.json()

    def _get_access_token(self) -> str:
        if self._token and self._token.expires_at > time.time():
            return self._token.token

        auth_header = base64.b64encode(f"{self._client_id}:{self._client_secret}".encode()).decode()
        payload = {"grant_type": "client_credentials"}
        headers = {"Authorization": f"Basic {auth_header}"}
        data = self._request("POST", SPOTIFY_TOKEN_URL, data=payload, headers=headers)
        token = data.get("access_token")
        expires_in = data.get("expires_in", 3600)
        if not token:
            raise SpotifyAPIError(500, "Spotify token response missing access_token")

        self._token = SpotifyAccessToken(token=token, expires_at=time.time() + int(expires_in) - 30)
        return token

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._get_access_token()}"}

    def get_track(self, track_id: str) -> dict[str, Any]:
        """Fetch track metadata from Spotify."""
        return self._request("GET", f"{SPOTIFY_API_BASE_URL}/tracks/{track_id}", headers=self._auth_headers())

    def get_audio_features(self, track_id: str) -> dict[str, Any]:
        """Fetch audio feature metrics for a track."""
        return self._request(
            "GET",
            f"{SPOTIFY_API_BASE_URL}/audio-features/{track_id}",
            headers=self._auth_headers(),
        )

    def get_audio_analysis(self, track_id: str) -> dict[str, Any]:
        """Fetch detailed audio analysis data for a track."""
        return self._request(
            "GET",
            f"{SPOTIFY_API_BASE_URL}/audio-analysis/{track_id}",
            headers=self._auth_headers(),
        )

    def get_artists(self, artist_ids: list[str]) -> dict[str, Any]:
        """Fetch metadata for a list of artists."""
        if not artist_ids:
            return {"artists": []}
        ids = ",".join(artist_ids)
        return self._request(
            "GET",
            f"{SPOTIFY_API_BASE_URL}/artists",
            params={"ids": ids},
            headers=self._auth_headers(),
        )


class MockSpotifyClient:
    """Mock client for local development without Spotify credentials."""

    def __init__(self) -> None:
        """Initialize the mock client."""
        self._track_template = {
            "id": "",
            "name": "Mock Track",
            "artists": [
                {"id": "mock-artist-1", "name": "Mock Artist One"},
                {"id": "mock-artist-2", "name": "Mock Artist Two"},
            ],
            "album": {"name": "Mock Album", "release_date": "2023-10-31"},
            "duration_ms": 215000,
            "explicit": False,
            "popularity": 42,
            "preview_url": "https://example.com/mock-preview.mp3",
            "external_urls": {"spotify": "https://open.spotify.com/track/mock"},
        }
        self._audio_features = {
            "tempo": 123.4,
            "key": 2,
            "mode": 1,
            "time_signature": 4,
            "energy": 0.78,
            "danceability": 0.64,
            "valence": 0.55,
            "acousticness": 0.12,
            "instrumentalness": 0.0,
            "liveness": 0.18,
            "loudness": -6.4,
            "speechiness": 0.04,
        }
        self._audio_analysis = {
            "track": {
                "tempo": 123.6,
                "key": 2,
                "mode": 1,
                "time_signature": 4,
                "loudness": -6.2,
                "duration": 215.0,
            }
        }
        self._artists = {
            "mock-artist-1": {
                "id": "mock-artist-1",
                "name": "Mock Artist One",
                "genres": ["electronic", "house"],
            },
            "mock-artist-2": {
                "id": "mock-artist-2",
                "name": "Mock Artist Two",
                "genres": ["dance", "pop"],
            },
        }

    def get_track(self, track_id: str) -> dict[str, Any]:
        """Return mock track metadata."""
        track = copy.deepcopy(self._track_template)
        track["id"] = track_id
        track["external_urls"]["spotify"] = f"https://open.spotify.com/track/{track_id}"
        return track

    def get_audio_features(self, track_id: str) -> dict[str, Any]:
        """Return mock audio features."""
        return copy.deepcopy(self._audio_features)

    def get_audio_analysis(self, track_id: str) -> dict[str, Any]:
        """Return mock audio analysis."""
        return copy.deepcopy(self._audio_analysis)

    def get_artists(self, artist_ids: list[str]) -> dict[str, Any]:
        """Return mock artist metadata for requested IDs."""
        artists = []
        for artist_id in artist_ids:
            if artist_id in self._artists:
                artists.append(copy.deepcopy(self._artists[artist_id]))
            else:
                artists.append({"id": artist_id, "name": "Unknown Artist", "genres": []})
        return {"artists": artists}
