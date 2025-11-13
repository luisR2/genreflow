"""Audio utility helpers."""

from __future__ import annotations

import librosa
import numpy as np
from librosa.feature import rhythm  # librosa >= 0.10


def estimate_bpm(
    y: np.ndarray,
    sr: int,
    preferred_min: float = 70.0,
    preferred_max: float = 190.0,
) -> float | None:
    """Estimate BPM using robust windowed tempo analysis (HPSS + windowed tempo + octave fold)."""
    if y is None or y.size == 0:
        return None

    # 1) Emphasize percussive content
    y_h, y_p = librosa.effects.hpss(y)
    y_perc = y_p

    # 2) Slide over windows, estimate tempo per window
    hop_length = 256
    win_s, hop_s = 15.0, 7.5
    win = int(win_s * sr)
    hop = int(hop_s * sr)
    bpms, weights = [], []

    for start in range(0, max(1, len(y_perc) - win + 1), hop):
        seg = y_perc[start : start + win]
        if seg.size < win // 2:
            continue

        oenv = librosa.onset.onset_strength(
            y=seg, sr=sr, hop_length=hop_length, aggregate=np.median
        )
        if oenv.size < 8 or not np.isfinite(oenv).all():
            continue

        # Use compat tempo function
        tempo = rhythm.tempo(
            onset_envelope=oenv,
            sr=sr,
            hop_length=hop_length,
            start_bpm=128.0,
            aggregate=None,  # return distribution
        )

        bpm_seg = float(np.median(tempo)) if np.size(tempo) > 1 else float(tempo)
        if not np.isfinite(bpm_seg):
            continue

        bpms.append(bpm_seg)
        weights.append(float(np.mean(oenv)))

    if not bpms:
        return None

    # 3) Fold tempos into preferred band to fix 1/2x & 2x errors
    def _fold_into_range(x: float) -> float:
        while x < preferred_min:
            x *= 2.0
        while x > preferred_max:
            x /= 2.0
        return x

    bpms_folded = np.array([_fold_into_range(x) for x in bpms], dtype=float)
    weights = np.array(weights, dtype=float)

    # 4) Weighted mode via histogram, then refine via weighted average near the mode
    bins = np.arange(preferred_min, preferred_max + 0.5, 0.5)
    hist, edges = np.histogram(bpms_folded, bins=bins, weights=weights)
    idx = int(np.argmax(hist))
    bpm_mode = 0.5 * (edges[idx] + edges[idx + 1])

    mask = np.abs(bpms_folded - bpm_mode) <= 2.0
    if np.any(mask):
        bpm_refined = float(np.average(bpms_folded[mask], weights=weights[mask]))
    else:
        bpm_refined = float(bpm_mode)

    # Snap to 0.1 BPM to reduce jitter
    return round(bpm_refined, 1)
