"""Prediction endpoint tests."""

import io

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from backend.app.app import app
from backend.app.routes_file import MAX_BATCH_SIZE, MAX_FILE_SIZE_BYTES


@pytest.fixture()
def client() -> TestClient:
    """Return a TestClient that exercises the full application lifespan."""
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sine_wav_bytes(freq: float = 440.0, sr: int = 16000, secs: float = 2.0) -> bytes:
    """Generate a simple sine wave clip encoded as WAV bytes."""
    t = np.linspace(0, secs, int(secs * sr), endpoint=False, dtype=np.float32)
    y = 0.5 * np.sin(2 * np.pi * freq * t)
    buf = io.BytesIO()
    sf.write(buf, y, sr, format="WAV")
    buf.seek(0)
    return buf.read()


def _silent_wav_bytes(sr: int = 16000, secs: float = 2.0) -> bytes:
    """Generate a silent (all-zeros) WAV clip."""
    y = np.zeros(int(secs * sr), dtype=np.float32)
    buf = io.BytesIO()
    sf.write(buf, y, sr, format="WAV")
    buf.seek(0)
    return buf.read()


# ---------------------------------------------------------------------------
# Happy-path tests
# ---------------------------------------------------------------------------


def test_predict_file_endpoint_ok(client: TestClient) -> None:
    """`POST /predict/file` returns BPM analysis for audio input."""
    wav = _sine_wav_bytes()
    files = {"file": ("tone.wav", wav, "audio/wav")}
    r = client.post("/predict/file", files=files)
    assert r.status_code == 200
    body = r.json()
    assert body["filename"] == "tone.wav"
    assert (body.get("bpm") is None) or isinstance(body.get("bpm"), (float, int))
    assert "analysis_time" in body
    assert isinstance(body["analysis_time"], (float, int))
    assert body["analysis_time"] > 0


def test_predict_files_bulk_endpoint_ok(client: TestClient) -> None:
    """`POST /predict/files` returns BPM analysis for multiple audio files (bulk)."""
    wav1 = _sine_wav_bytes(freq=440.0)
    wav2 = _sine_wav_bytes(freq=880.0)
    files = [
        ("files", ("tone1.wav", wav1, "audio/wav")),
        ("files", ("tone2.wav", wav2, "audio/wav")),
    ]
    r = client.post("/predict/files", files=files)
    assert r.status_code == 200
    body = r.json()
    assert "results" in body
    assert isinstance(body["results"], list)
    assert len(body["results"]) == 2
    filenames = [result["filename"] for result in body["results"]]
    assert set(filenames) == {"tone1.wav", "tone2.wav"}
    for result in body["results"]:
        assert (result.get("bpm") is None) or isinstance(result.get("bpm"), (float, int))
        assert "analysis_time" in result
        assert isinstance(result["analysis_time"], (float, int))
        assert result["analysis_time"] > 0
    assert "analysis_time" in body
    assert isinstance(body["analysis_time"], (float, int))
    sum_individual = sum(res["analysis_time"] for res in body["results"])
    assert abs(body["analysis_time"] - sum_individual) < 1e-3


# ---------------------------------------------------------------------------
# Negative-path: extension validation
# ---------------------------------------------------------------------------


def test_predict_file_rejects_unsupported_extension(client: TestClient) -> None:
    """Files with unsupported extensions are rejected with 400."""
    wav = _sine_wav_bytes()
    files = {"file": ("track.ogg", wav, "audio/ogg")}
    r = client.post("/predict/file", files=files)
    assert r.status_code == 400
    assert "Unsupported file type" in r.json()["detail"]


# ---------------------------------------------------------------------------
# Negative-path: magic bytes / MIME validation
# ---------------------------------------------------------------------------


def test_predict_file_rejects_wrong_magic_bytes(client: TestClient) -> None:
    """Files whose content does not match a known audio format are rejected with 415."""
    fake_audio = b"This is plain text, not audio content at all."
    files = {"file": ("not_audio.wav", fake_audio, "audio/wav")}
    r = client.post("/predict/file", files=files)
    assert r.status_code == 415


# ---------------------------------------------------------------------------
# Negative-path: file size limit
# ---------------------------------------------------------------------------


def test_predict_file_rejects_oversized_file(client: TestClient) -> None:
    """Files exceeding the size limit are rejected with 413."""
    oversized = b"\x00" * (MAX_FILE_SIZE_BYTES + 1)
    files = {"file": ("big.wav", oversized, "audio/wav")}
    r = client.post("/predict/file", files=files)
    assert r.status_code == 413
    assert "too large" in r.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Negative-path: batch size limit
# ---------------------------------------------------------------------------


def test_predict_files_rejects_oversized_batch(client: TestClient) -> None:
    """Batches exceeding the maximum file count are rejected with 413."""
    wav = _sine_wav_bytes()
    files = [("files", (f"tone{i}.wav", wav, "audio/wav")) for i in range(MAX_BATCH_SIZE + 1)]
    r = client.post("/predict/files", files=files)
    assert r.status_code == 413
    assert "Too many files" in r.json()["detail"]


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_predict_file_silent_audio(client: TestClient) -> None:
    """Silent audio returns 200; BPM may be None since there is no detectable beat."""
    wav = _silent_wav_bytes()
    files = {"file": ("silent.wav", wav, "audio/wav")}
    r = client.post("/predict/file", files=files)
    assert r.status_code == 200
    body = r.json()
    assert body["filename"] == "silent.wav"
    assert (body.get("bpm") is None) or isinstance(body.get("bpm"), (float, int))


def test_predict_file_corrupt_file(client: TestClient) -> None:
    """Corrupt WAV data (valid extension, invalid content) returns an error."""
    corrupt = b"RIFF\x00\x00\x00\x00WAVEfmt \xff\xff\xff\xff"  # truncated/invalid WAV
    files = {"file": ("corrupt.wav", corrupt, "audio/wav")}
    r = client.post("/predict/file", files=files)
    # The file may be rejected at MIME validation (415) or processing (400)
    assert r.status_code in (400, 415)


def test_predict_file_empty_file(client: TestClient) -> None:
    """An empty file (zero bytes) is rejected before or during processing."""
    files = {"file": ("empty.wav", b"", "audio/wav")}
    r = client.post("/predict/file", files=files)
    assert r.status_code in (400, 415)
