"""Prediction endpoint tests."""

import io

import numpy as np
import soundfile as sf
from backend.app.app import app
from fastapi.testclient import TestClient

client = TestClient(app)


def _sine_wav_bytes(freq: float = 440.0, sr: int = 16000, secs: float = 2.0) -> bytes:
    """Generate a simple sine wave clip encoded as WAV bytes."""
    t = np.linspace(0, secs, int(secs * sr), endpoint=False, dtype=np.float32)
    y = 0.5 * np.sin(2 * np.pi * freq * t)
    buf = io.BytesIO()
    sf.write(buf, y, sr, format="WAV")
    buf.seek(0)
    return buf.read()


def test_predict_file_endpoint_ok() -> None:
    """`POST /predict/file` returns BPM analysis for audio input."""
    wav = _sine_wav_bytes()
    files = {"file": ("tone.wav", wav, "audio/wav")}
    r = client.post("/predict/file", files=files)
    assert r.status_code == 200
    body = r.json()
    assert body["filename"] == "tone.wav"
    # BPM may be None for synthetic tones; allow None or a float
    assert (body.get("bpm") is None) or isinstance(body.get("bpm"), (float, int))
    assert "analysis_time" in body
    assert isinstance(body["analysis_time"], (float, int))
    assert body["analysis_time"] > 0


def test_predict_files_bulk_endpoint_ok() -> None:
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
    # Per-file checks
    for result in body["results"]:
        assert (result.get("bpm") is None) or isinstance(result.get("bpm"), (float, int))
        assert "analysis_time" in result
        assert isinstance(result["analysis_time"], (float, int))
        assert result["analysis_time"] > 0
    # Batch timing
    assert "analysis_time" in body
    assert isinstance(body["analysis_time"], (float, int))
    sum_individual = sum(res["analysis_time"] for res in body["results"])
    assert abs(body["analysis_time"] - sum_individual) < 1e-3  # allow small float error
