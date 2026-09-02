"""Benchmark harness for Predictor BPM analysis.

Times _load_audio and estimate_bpm separately and checks BPM accuracy against
synthetic click tracks of known tempo. Use it to confirm the <10s per track
budget on a given machine -- in particular on the Raspberry Pi cluster, which is
substantially slower than a dev laptop.

Usage:
    cd backend && PYTHONPATH=.. poetry run python ../scripts/bench_bpm.py
    ... --real /path/to/track.wav   # add a real file to the run
"""

from __future__ import annotations

import argparse
import io
import time

import numpy as np
import soundfile as sf

from backend.app.predict import Predictor

REAL_TRACK: str | None = None  # optional real track; override with --real


def click_track(bpm: float, secs: float, sr: int = 44100, seed: int = 0) -> bytes:
    """Synthesize a percussive track at a known BPM.

    Kick on every beat, hat on every off-beat, plus a bass drone and noise floor,
    so onset detection has realistic material to work with.
    """
    rng = np.random.default_rng(seed)
    n = int(secs * sr)
    y = np.zeros(n, dtype=np.float32)

    beat_period = 60.0 / bpm
    # Kick: decaying 60 Hz sine burst
    kick_len = int(0.12 * sr)
    kt = np.arange(kick_len) / sr
    kick = (np.sin(2 * np.pi * 60 * kt) * np.exp(-kt * 28)).astype(np.float32)
    # Hat: decaying filtered noise burst
    hat_len = int(0.04 * sr)
    ht = np.arange(hat_len) / sr
    hat = (rng.standard_normal(hat_len) * np.exp(-ht * 120) * 0.35).astype(np.float32)

    t = 0.0
    while t < secs:
        i = int(t * sr)
        end = min(i + kick_len, n)
        y[i:end] += kick[: end - i]
        # off-beat hat
        j = int((t + beat_period / 2) * sr)
        if j < n:
            end = min(j + hat_len, n)
            y[j:end] += hat[: end - j]
        t += beat_period

    # Harmonic bed + noise floor so HPSS has something to separate
    full_t = np.arange(n) / sr
    y += 0.12 * np.sin(2 * np.pi * 110 * full_t).astype(np.float32)
    y += 0.02 * rng.standard_normal(n).astype(np.float32)
    y /= np.max(np.abs(y))

    buf = io.BytesIO()
    sf.write(buf, y, sr, format="WAV")
    buf.seek(0)
    return buf.read()


def bench_one(p: Predictor, data: bytes, label: str, truth: float | None) -> dict:
    """Time load + estimate for one clip and compare against ground truth."""
    t0 = time.monotonic()
    y, _ = p._load_audio(data)
    t1 = time.monotonic()
    bpm = Predictor.estimate_bpm(y, sr=p.sr)
    t2 = time.monotonic()

    load_s, est_s = t1 - t0, t2 - t1
    total = load_s + est_s

    if truth is None:
        acc = "   n/a"
    elif bpm is None:
        acc = "  FAIL"
    else:
        # Accept octave-equivalent answers (half/double time)
        cands = [truth, truth * 2, truth / 2]
        err = min(abs(bpm - c) for c in cands)
        acc = "    OK" if err <= 1.5 else f"OFF {bpm - truth:+.1f}"

    flag = "  <-- OVER 10s" if total > 10 else ""
    print(
        f"{label:<26} load {load_s:6.2f}s  est {est_s:6.2f}s  "
        f"total {total:6.2f}s   bpm {str(bpm):>7}  {acc}{flag}"
    )
    return {"label": label, "load": load_s, "est": est_s, "total": total, "bpm": bpm, "truth": truth}


def main() -> None:
    """Run the benchmark suite."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--real", default=REAL_TRACK, help="optional real audio file to benchmark")
    args = ap.parse_args()

    p = Predictor.load()
    rows = []

    print("=" * 96)
    print("SYNTHETIC CLICK TRACKS (known BPM)")
    print("=" * 96)
    for bpm in (90.0, 128.0, 174.0):
        for secs in (30.0, 180.0, 300.0):
            data = click_track(bpm, secs)
            rows.append(bench_one(p, data, f"{bpm:g} BPM / {secs:g}s", bpm))

    print()
    print("=" * 96)
    print("REAL TRACK")
    print("=" * 96)
    if not args.real:
        print("no real track given (pass --real PATH to include one)")
    else:
        try:
            with open(args.real, "rb") as fh:
                real = fh.read()
            info = sf.info(io.BytesIO(real))
            rows.append(bench_one(p, real, f"real {info.duration:.0f}s {info.samplerate}Hz", None))
        except Exception as e:  # noqa: BLE001
            print(f"skipped real track: {e}")

    print()
    print("=" * 96)
    over = [r for r in rows if r["total"] > 10]
    worst = max(rows, key=lambda r: r["total"])
    print(f"clips over the 10s budget: {len(over)}/{len(rows)}")
    print(
        f"worst case: {worst['label']} at {worst['total']:.2f}s "
        f"(load {worst['load']:.2f}s + est {worst['est']:.2f}s)"
    )
    print("=" * 96)


if __name__ == "__main__":
    main()
