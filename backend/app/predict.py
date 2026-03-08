"""GenreFlow music genre predictor utilities.

This module provides a simple audio genre classification system that:
1. Loads and prepares audio files (normalizing, resampling, splitting)
2. Extracts simple features from each window of audio
3. Produces a probability-like prediction for each window and averages them
4. Returns the top predicted genres

Note: Currently uses a heuristic model. Will be replaced with ONNX/TFLite later.
"""

from __future__ import annotations

import asyncio
import io
import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

import librosa
import librosa.feature.rhythm as librosa_rhythm
import numpy as np
import numpy.typing as npt
import soundfile as sf

from backend.app.schemas import BPMResult

if TYPE_CHECKING:
    from pathlib import Path

# Configure logging
logger = logging.getLogger(__name__)

# Constants
DEFAULT_SAMPLE_RATE = 16000
DEFAULT_N_MELS = 64
DEFAULT_WINDOW_SIZE = 10.0  # seconds


@dataclass
class PredictorConfig:
    """Configuration for the Predictor class."""

    sample_rate: int = DEFAULT_SAMPLE_RATE
    n_mels: int = DEFAULT_N_MELS
    window_size: float = DEFAULT_WINDOW_SIZE
    min_clip_length: float = 1.0  # minimum audio length in seconds


class Predictor:
    """Audio genre prediction using spectral features.

    Args:
        sample_rate: Target sample rate for audio processing
        n_mels: Number of mel bands for feature extraction
        config: Optional predictor configuration
    """

    def __init__(
        self,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        n_mels: int = DEFAULT_N_MELS,
        config: PredictorConfig | None = None,
    ) -> None:
        """Initialize the predictor with configuration and defaults."""
        self.config = config or PredictorConfig(sample_rate=sample_rate, n_mels=n_mels)
        self.sr = self.config.sample_rate

    @classmethod
    def load(cls, model_path: Path | None = None) -> Predictor:
        """Load a predictor instance, optionally with a pre-trained model.

        Args:
            model_path: Optional path to ONNX/TFLite model file

        Returns:
            Predictor: Initialized predictor instance

        Note:
            Currently returns a heuristic model. Will load actual model later.
        """
        logger.info("Initializing predictor")
        return cls()

    def _load_audio(self, audio_bytes: bytes) -> tuple[npt.NDArray[np.float32], int]:
        """Load and preprocess audio from bytes.

        Args:
            audio_bytes: Raw audio file bytes

        Returns:
            Tuple containing:
            - Normalized audio signal as float32 numpy array
            - Sample rate

        Raises:
            ValueError: If audio file is invalid or empty
        """
        try:
            buf = io.BytesIO(audio_bytes)
            y, sr = sf.read(buf, dtype="float32", always_2d=False)

            if len(y) == 0:
                raise ValueError("Empty audio file")

            # Convert stereo to mono by averaging channels
            if y.ndim > 1:
                y = y.mean(axis=1)

            # Resample if needed
            if sr != self.sr:
                logger.debug(f"Resampling audio from {sr}Hz to {self.sr}Hz")
                y = librosa.resample(y, orig_sr=sr, target_sr=self.sr)
                sr = self.sr

            # Normalize audio
            max_amp = np.max(np.abs(y))
            if max_amp > 0:
                y = y / max_amp

            if len(y) < self.config.min_clip_length * self.sr:
                raise ValueError(
                    f"Audio clip too short. Must be at least {self.config.min_clip_length} seconds"
                )

            return y, sr

        except Exception as e:
            raise ValueError(f"Failed to load audio: {str(e)}") from e

    async def predict_bytes(self, audio_bytes: bytes, filename: str = "unknown") -> BPMResult:
        """Analyze BPM from audio file bytes. Ignores genre analysis.

        Args:
            audio_bytes: Raw audio file bytes
            filename: Name of the uploaded/processed file

        Returns:
            BPMResult: Tempo analysis result
        """
        start_time = time.monotonic()
        y, _ = await asyncio.to_thread(self._load_audio, audio_bytes)
        bpm = await asyncio.to_thread(Predictor.estimate_bpm, y, sr=self.sr)
        analysis_time = time.monotonic() - start_time
        return BPMResult(filename=filename, bpm=bpm, analysis_time=analysis_time)

    @staticmethod
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

            oenv = librosa.onset.onset_strength(y=seg, sr=sr, hop_length=hop_length, aggregate=np.median)
            if oenv.size < 8 or not np.isfinite(oenv).all():
                continue

            tempo = librosa_rhythm.tempo(
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
