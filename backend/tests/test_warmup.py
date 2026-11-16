"""Startup warm-up tests: the toggle, the analysis, and its failure mode."""

import asyncio

import pytest
from fastapi.testclient import TestClient

from backend.app.app import WARMUP_ENV_VAR, _warmup_enabled, app
from backend.app.predict import WARMUP_BPM, Predictor

# The warm-up clip is synthesized at a known tempo, so a correct estimate is
# proof the tempo path actually ran rather than returning early.
TOL = 2.0


# ---------------------------------------------------------------------------
# Toggle
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["0", "false", "FALSE", "no", "off", " off "])
def test_warmup_disabled_by_falsy_values(monkeypatch, value) -> None:
    monkeypatch.setenv(WARMUP_ENV_VAR, value)
    assert _warmup_enabled() is False


@pytest.mark.parametrize("value", ["1", "true", "yes", "anything"])
def test_warmup_enabled_by_other_values(monkeypatch, value) -> None:
    monkeypatch.setenv(WARMUP_ENV_VAR, value)
    assert _warmup_enabled() is True


def test_warmup_enabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv(WARMUP_ENV_VAR, raising=False)
    assert _warmup_enabled() is True


# ---------------------------------------------------------------------------
# The warm-up itself
# ---------------------------------------------------------------------------


def test_warm_up_analyses_the_synthetic_clip() -> None:
    """The warm-up must run the real tempo path, not a no-op."""
    bpm = asyncio.run(Predictor.load().warm_up())
    assert bpm is not None
    assert abs(bpm - WARMUP_BPM) <= TOL


def test_warmup_signal_is_normalised_and_long_enough() -> None:
    predictor = Predictor.load()
    y = predictor._warmup_signal(predictor.sr)
    assert len(y) / predictor.sr >= 5.0  # MIN_TEMPO_WINDOW_SECONDS
    assert pytest.approx(1.0, abs=1e-6) == float(abs(y).max())


def test_warm_up_swallows_failures(monkeypatch) -> None:
    """A broken warm-up must not be able to stop the service from starting."""

    def _boom(*args, **kwargs):
        raise RuntimeError("numba exploded")

    monkeypatch.setattr(Predictor, "estimate_bpm", staticmethod(_boom))
    assert asyncio.run(Predictor.load().warm_up()) is None


# ---------------------------------------------------------------------------
# Lifespan wiring
# ---------------------------------------------------------------------------


def test_lifespan_warms_up_when_enabled(monkeypatch) -> None:
    calls: list[int] = []

    async def _spy(self) -> None:
        calls.append(1)

    monkeypatch.setenv(WARMUP_ENV_VAR, "1")
    monkeypatch.setattr(Predictor, "warm_up", _spy)
    with TestClient(app) as client:
        assert client.get("/readyz").status_code == 200
    assert calls == [1]


def test_lifespan_skips_warmup_when_disabled(monkeypatch) -> None:
    calls: list[int] = []

    async def _spy(self) -> None:
        calls.append(1)

    monkeypatch.setenv(WARMUP_ENV_VAR, "0")
    monkeypatch.setattr(Predictor, "warm_up", _spy)
    with TestClient(app) as client:
        assert client.get("/readyz").status_code == 200
    assert calls == []


def test_predictor_is_published_only_after_warmup(monkeypatch) -> None:
    """readyz must never report ready while the JIT cost is still outstanding."""
    seen: list[object] = []

    async def _spy(self) -> None:
        seen.append(getattr(app.state, "predictor", None))

    monkeypatch.setenv(WARMUP_ENV_VAR, "1")
    monkeypatch.setattr(Predictor, "warm_up", _spy)
    monkeypatch.setattr(app.state, "predictor", None, raising=False)
    with TestClient(app):
        pass
    assert seen == [None]
