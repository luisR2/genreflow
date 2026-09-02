"""Tempo estimation tests: accuracy, excerpt bounding, and short-clip handling."""

import numpy as np
import pytest

from backend.app.predict import DEFAULT_MAX_ANALYSIS_SECONDS, Predictor

SR = 16000
# Tolerance in BPM. The estimator snaps to 0.1 BPM but the tempogram's lag
# quantisation still leaves ~1 BPM of slack at the top of the range.
TOL = 2.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _click_track(bpm: float, secs: float, sr: int = SR, seed: int = 0) -> np.ndarray:
    """Synthesize a normalized percussive track at a known tempo.

    Kick on every beat and hat on the off-beat, over a quiet harmonic bed, so the
    onset envelope has realistic material to lock onto.
    """
    rng = np.random.default_rng(seed)
    n = int(secs * sr)
    y = np.zeros(n, dtype=np.float32)

    kick_len = int(0.12 * sr)
    kt = np.arange(kick_len) / sr
    kick = (np.sin(2 * np.pi * 60 * kt) * np.exp(-kt * 28)).astype(np.float32)

    hat_len = int(0.04 * sr)
    ht = np.arange(hat_len) / sr
    hat = (rng.standard_normal(hat_len) * np.exp(-ht * 120) * 0.35).astype(np.float32)

    beat_period = 60.0 / bpm
    t = 0.0
    while t < secs:
        i = int(t * sr)
        end = min(i + kick_len, n)
        y[i:end] += kick[: end - i]
        j = int((t + beat_period / 2) * sr)
        if j < n:
            end = min(j + hat_len, n)
            y[j:end] += hat[: end - j]
        t += beat_period

    full_t = np.arange(n) / sr
    y += 0.12 * np.sin(2 * np.pi * 110 * full_t).astype(np.float32)
    y += 0.02 * rng.standard_normal(n).astype(np.float32)
    return (y / np.max(np.abs(y))).astype(np.float32)


def _close_to(got: float, truth: float, tol: float = TOL) -> bool:
    """Compare BPM allowing octave-equivalent (half/double time) answers."""
    return min(abs(got - c) for c in (truth, truth * 2, truth / 2)) <= tol


# ---------------------------------------------------------------------------
# Accuracy
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bpm", [90.0, 128.0, 174.0])
def test_estimate_bpm_recovers_known_tempo(bpm):
    """Estimator recovers the tempo of a synthetic click track.

    174 BPM is the regression guard for the onset hop length: at the previous hop
    of 256 the tempogram's integer lag spacing forced this case to 170.5.
    """
    y = _click_track(bpm, 60.0)
    got = Predictor.estimate_bpm(y, sr=SR)
    assert got is not None
    assert _close_to(got, bpm), f"expected ~{bpm}, got {got}"


def test_estimate_bpm_is_stable_across_repeat_calls():
    """Repeated analysis of the same signal yields the same tempo."""
    y = _click_track(128.0, 60.0)
    assert Predictor.estimate_bpm(y, sr=SR) == Predictor.estimate_bpm(y, sr=SR)


# ---------------------------------------------------------------------------
# Excerpt bounding
# ---------------------------------------------------------------------------


def test_estimate_bpm_is_invariant_to_track_length():
    """Trimming to a centred excerpt does not change the reported tempo.

    Guards the performance optimisation: analysis cost is capped by excerpting,
    which is only sound if a longer track still reports the same BPM.
    """
    short = Predictor.estimate_bpm(_click_track(128.0, 60.0), sr=SR)
    long = Predictor.estimate_bpm(_click_track(128.0, 240.0), sr=SR)
    assert short is not None and long is not None
    assert short == long


def test_centre_excerpt_caps_length_and_takes_from_middle():
    """Excerpt is capped to the limit and drawn from the centre of the signal."""
    y = np.arange(100 * SR, dtype=np.float32)
    out = Predictor._centre_excerpt(y, SR, 10.0)
    assert len(out) == 10 * SR
    # Centre of a 100s signal, 10s wide, starts at 45s
    assert out[0] == pytest.approx(45 * SR)


def test_centre_excerpt_passes_through_shorter_signal():
    """A signal already under the limit is returned unchanged."""
    y = np.arange(5 * SR, dtype=np.float32)
    out = Predictor._centre_excerpt(y, SR, 60.0)
    assert len(out) == len(y)


def test_centre_excerpt_disabled_by_non_positive_limit():
    """A non-positive limit disables trimming."""
    y = np.arange(100 * SR, dtype=np.float32)
    assert len(Predictor._centre_excerpt(y, SR, 0.0)) == len(y)


def test_default_analysis_cap_is_applied():
    """A track longer than the cap is trimmed to it before analysis."""
    y = _click_track(128.0, DEFAULT_MAX_ANALYSIS_SECONDS * 3, sr=SR)
    trimmed = Predictor._centre_excerpt(y, SR, DEFAULT_MAX_ANALYSIS_SECONDS)
    assert len(trimmed) == int(DEFAULT_MAX_ANALYSIS_SECONDS * SR)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_estimate_bpm_handles_clip_shorter_than_window():
    """Clips below the 15s analysis window are analysed whole rather than skipped."""
    got = Predictor.estimate_bpm(_click_track(128.0, 6.0), sr=SR)
    assert got is not None
    assert _close_to(got, 128.0)


def test_estimate_bpm_returns_none_for_very_short_clip():
    """Clips too short to support an estimate return None instead of a guess."""
    assert Predictor.estimate_bpm(_click_track(128.0, 2.0), sr=SR) is None


def test_estimate_bpm_returns_none_for_empty_signal():
    """An empty signal yields no estimate."""
    assert Predictor.estimate_bpm(np.array([], dtype=np.float32), sr=SR) is None


def test_estimate_bpm_returns_none_for_silence():
    """Silence has no detectable beat."""
    assert Predictor.estimate_bpm(np.zeros(30 * SR, dtype=np.float32), sr=SR) is None


def test_hpss_remains_available_as_an_option():
    """HPSS is off by default but still selectable, and agrees on clear material."""
    y = _click_track(128.0, 30.0)
    assert _close_to(Predictor.estimate_bpm(y, sr=SR, use_hpss=True), 128.0)
