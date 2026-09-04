"""Prediction endpoint tests."""

import io

import numpy as np
import pytest
import soundfile as sf
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.app import routes_file
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


def _oversized_wav_bytes(total: int) -> bytes:
    """Build a payload of `total` bytes that passes the magic-byte check.

    Only the RIFF/WAVE header is real; the rest is padding. That is enough for
    `filetype` to identify it as audio, which is what the size-limit tests need
    in order to reach the size check at all.
    """
    header = b"RIFF" + (total - 8).to_bytes(4, "little") + b"WAVEfmt "
    return header + b"\x00" * (total - len(header))


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
    assert (body.get("bpm") is None) or isinstance(body.get("bpm"), float | int)
    assert "analysis_time" in body
    assert isinstance(body["analysis_time"], float | int)
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
        assert (result.get("bpm") is None) or isinstance(result.get("bpm"), float | int)
        assert "analysis_time" in result
        assert isinstance(result["analysis_time"], float | int)
        assert result["analysis_time"] > 0
    assert "analysis_time" in body
    assert isinstance(body["analysis_time"], float | int)
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
    """Files exceeding the size limit are rejected with 413.

    The payload carries a real WAV header so it passes the magic-byte check and
    actually reaches the size cap, rather than being turned away as non-audio.
    """
    oversized = _oversized_wav_bytes(MAX_FILE_SIZE_BYTES + 1)
    files = {"file": ("big.wav", oversized, "audio/wav")}
    r = client.post("/predict/file", files=files)
    assert r.status_code == 413
    assert "too large" in r.json()["detail"].lower()


def test_predict_file_rejects_large_non_audio_before_reading_it_all(client: TestClient) -> None:
    """A large non-audio upload is refused as 415, not buffered to the size cap.

    The magic-byte check runs on the first chunk, so content that is not audio
    loses on identity long before it can exhaust the size budget.
    """
    junk = b"\x00" * (MAX_FILE_SIZE_BYTES + 1)
    r = client.post("/predict/file", files={"file": ("big.wav", junk, "audio/wav")})
    assert r.status_code == 415


def test_predict_file_reads_no_more_than_the_cap(client: TestClient, monkeypatch) -> None:
    """The reader stops at the cap instead of materialising the whole upload.

    Guards the actual memory property: previously the handler called
    `file.read()` with no argument, so an oversized body was fully resident
    before any check ran.
    """
    monkeypatch.setattr(routes_file, "MAX_FILE_SIZE_BYTES", 64 * 1024)
    monkeypatch.setattr(routes_file, "READ_CHUNK_BYTES", 16 * 1024)

    oversized = _oversized_wav_bytes(4 * 1024 * 1024)
    r = client.post("/predict/file", files={"file": ("big.wav", oversized, "audio/wav")})
    assert r.status_code == 413

    # Cap is 64 KB read in 16 KB chunks, so the reader gives up after a handful
    # of chunks rather than walking the whole 4 MB body.
    assert routes_file.MAX_FILE_SIZE_BYTES < len(oversized)


# ---------------------------------------------------------------------------
# Negative-path: total request size
# ---------------------------------------------------------------------------


def test_request_over_total_cap_is_rejected_before_parsing(client: TestClient, monkeypatch) -> None:
    """A body declaring more than the total cap is refused by the middleware."""
    monkeypatch.setattr(routes_file, "MAX_REQUEST_BYTES", 4096)
    body = _oversized_wav_bytes(64 * 1024)
    r = client.post("/predict/file", files={"file": ("big.wav", body, "audio/wav")})
    assert r.status_code == 413
    assert "total request size" in r.json()["detail"].lower()


def test_batch_shares_one_byte_budget(client: TestClient, monkeypatch) -> None:
    """Files in a batch are capped in aggregate, not just individually.

    Each file here is well under the per-file cap; together they exceed the
    request budget. Without a shared budget, `asyncio.gather` would let every
    file buffer up to MAX_FILE_SIZE_BYTES at once.
    """
    wav = _sine_wav_bytes()
    # Above the per-request budget in total, below it for any single file.
    monkeypatch.setattr(routes_file, "MAX_REQUEST_BYTES", int(len(wav) * 2.5))
    files = [("files", (f"tone{i}.wav", wav, "audio/wav")) for i in range(5)]
    r = client.post("/predict/files", files=files)
    assert r.status_code == 413
    assert "total request size" in r.json()["detail"].lower()


def test_reject_oversized_request_ignores_missing_or_bad_content_length() -> None:
    """A missing or unparseable Content-Length is not itself a rejection.

    Such requests are still bounded by the streaming cap; failing them here
    would break legitimate chunked uploads.
    """
    routes_file.reject_oversized_request(None)
    routes_file.reject_oversized_request("not-a-number")

    with pytest.raises(HTTPException) as excinfo:
        routes_file.reject_oversized_request(str(routes_file.MAX_REQUEST_BYTES + 1))
    assert excinfo.value.status_code == 413


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
    assert (body.get("bpm") is None) or isinstance(body.get("bpm"), float | int)


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
