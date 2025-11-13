"""Prediction endpoint tests."""

import io

import numpy as np
import soundfile as sf
from fastapi.testclient import TestClient
from server.app import app

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
    """`POST /predict/file` returns predictions for audio input."""
    wav = _sine_wav_bytes()
    files = {"file": ("tone.wav", wav, "audio/wav")}
    r = client.post("/predict/file?top_k=3", files=files)
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "file"
    assert body["filename"] == "tone.wav"

    # Response uses `top_k` list of {label, score}
    assert isinstance(body.get("top_k"), list)
    top_k = body.get("top_k", [])
    # We asked for top_k=3
    assert len(top_k) == 3
    for item in top_k:
        assert "label" in item and isinstance(item["label"], str)
        assert "score" in item and isinstance(item["score"], (float, int))

    # BPM may be None for synthetic tones; allow None or a float
    assert (body.get("bpm") is None) or isinstance(body.get("bpm"), (float, int))
