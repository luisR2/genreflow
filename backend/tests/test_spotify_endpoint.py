"""Spotify metadata endpoint tests."""

from fastapi.testclient import TestClient

from backend.app.app import app

client = TestClient(app)


class DummySpotifyClient:
    """Stub Spotify client for testing."""

    def get_track(self, track_id: str) -> dict[str, object]:
        return {
            "id": track_id,
            "name": "Test Song",
            "artists": [{"id": "artist1", "name": "Test Artist"}],
            "album": {"name": "Test Album", "release_date": "2024-01-01"},
            "duration_ms": 123000,
            "explicit": False,
            "popularity": 55,
            "preview_url": "https://example.com/preview.mp3",
            "external_urls": {"spotify": "https://open.spotify.com/track/abc123"},
        }

    def get_audio_features(self, track_id: str) -> dict[str, object]:
        return {
            "tempo": 128.0,
            "key": 9,
            "mode": 1,
            "time_signature": 4,
            "energy": 0.8,
            "danceability": 0.7,
            "valence": 0.6,
            "acousticness": 0.2,
            "instrumentalness": 0.0,
            "liveness": 0.1,
            "loudness": -5.2,
            "speechiness": 0.05,
        }

    def get_audio_analysis(self, track_id: str) -> dict[str, object]:
        return {
            "track": {
                "tempo": 128.1,
                "key": 9,
                "mode": 1,
                "time_signature": 4,
                "loudness": -5.0,
                "duration": 123.0,
            }
        }

    def get_artists(self, artist_ids: list[str]) -> dict[str, object]:
        return {"artists": [{"id": "artist1", "genres": ["house", "dance"]}]}


def _override_client() -> DummySpotifyClient:
    return DummySpotifyClient()


def test_spotify_track_info_ok(monkeypatch) -> None:
    """`POST /spotify/track-info` returns track metadata and audio features."""
    monkeypatch.setattr("backend.app.spotify_routes._get_spotify_client", _override_client)
    payload = {"track_url": "https://open.spotify.com/track/aaaaaaaaaaaaaaaaaaaaaa"}
    response = client.post("/spotify/track-info", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["track_id"] == "aaaaaaaaaaaaaaaaaaaaaa"
    assert body["name"] == "Test Song"
    assert body["genres"] == ["dance", "house"]
    assert body["audio_features"]["tempo"] == 128.0
    assert body["audio_features"]["key_name"] == "A"
    assert body["analysis_summary"]["tempo"] == 128.1


def test_spotify_track_info_with_mock_env(monkeypatch) -> None:
    """`POST /spotify/track-info` uses mock data when enabled."""
    monkeypatch.setenv("SPOTIFY_USE_MOCK", "1")
    payload = {"track_id": "bbbbbbbbbbbbbbbbbbbbbb"}
    response = client.post("/spotify/track-info", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["track_id"] == "bbbbbbbbbbbbbbbbbbbbbb"
    assert body["name"] == "Mock Track"
    assert body["audio_features"]["tempo"] == 123.4
    assert body["analysis_summary"]["tempo"] == 123.6


def test_spotify_track_info_missing_input() -> None:
    """`POST /spotify/track-info` rejects missing track input."""
    response = client.post("/spotify/track-info", json={})
    assert response.status_code == 422
