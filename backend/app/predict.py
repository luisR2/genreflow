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
from functools import partial
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

# Tempo analysis tuning.
#
# Analysis is capped to a centred excerpt: tempo is near-stationary in most
# tracks, so a representative slice yields the same answer as the full signal
# while keeping runtime constant regardless of track length.
DEFAULT_MAX_ANALYSIS_SECONDS = 60.0

# Hop length for the onset envelope, in samples. This sets the frame rate of the
# tempogram and therefore the lag quantisation of the tempo estimate. At 16 kHz a
# hop of 256 gives 62.5 frames/s, where neighbouring integer lags near 174 BPM are
# ~8 BPM apart and the estimate snaps to 170.5. A hop of 128 doubles the frame rate
# and resolves those tempos correctly.
DEFAULT_TEMPO_HOP_LENGTH = 128

# Sliding analysis window over the excerpt, in seconds.
DEFAULT_TEMPO_WINDOW_SECONDS = 15.0
DEFAULT_TEMPO_STRIDE_SECONDS = 7.5

# Shortest signal that still supports a windowed tempo estimate. Below the normal
# window length the whole clip is used as a single window instead of being skipped.
MIN_TEMPO_WINDOW_SECONDS = 5.0

# Minimum mean onset-envelope energy for a window to count towards the estimate.
# Guards against silent input, whose all-zero envelope is finite and would
# otherwise contribute a zero-weight vote and yield a fabricated tempo.
MIN_ONSET_ENERGY = 1e-6

# Harmonic/percussive separation is disabled by default. It dominated runtime
# (~91% of analysis time on a 5 minute track) without changing the estimate on
# the benchmark material, so it is opt-in rather than always-on.
DEFAULT_USE_HPSS = False


@dataclass
class PredictorConfig:
    """Configuration for the Predictor class."""

    sample_rate: int = DEFAULT_SAMPLE_RATE
    n_mels: int = DEFAULT_N_MELS
    window_size: float = DEFAULT_WINDOW_SIZE
    min_clip_length: float = 1.0  # minimum audio length in seconds
    max_analysis_seconds: float = DEFAULT_MAX_ANALYSIS_SECONDS
    tempo_hop_length: int = DEFAULT_TEMPO_HOP_LENGTH
    use_hpss: bool = DEFAULT_USE_HPSS


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
        bpm = await asyncio.to_thread(
            partial(
                Predictor.estimate_bpm,
                y,
                sr=self.sr,
                max_analysis_seconds=self.config.max_analysis_seconds,
                hop_length=self.config.tempo_hop_length,
                use_hpss=self.config.use_hpss,
            )
        )
        analysis_time = time.monotonic() - start_time
        logger.debug("Analysed %s in %.2fs -> %s BPM", filename, analysis_time, bpm)
        return BPMResult(filename=filename, bpm=bpm, analysis_time=analysis_time)

    @staticmethod
    def _centre_excerpt(y: npt.NDArray[np.float32], sr: int, max_seconds: float) -> npt.NDArray[np.float32]:
        """Return at most max_seconds of audio taken from the middle of the signal.

        The middle is preferred over the head because intros are frequently sparse,
        ambient or beatless, which biases a tempo estimate taken from the start.

        Args:
            y: Audio signal.
            sr: Sample rate of ``y``.
            max_seconds: Maximum excerpt length. Non-positive disables trimming.

        Returns:
            The excerpt, or ``y`` unchanged when it is already short enough.
        """
        if max_seconds <= 0:
            return y
        limit = int(max_seconds * sr)
        if len(y) <= limit:
            return y
        start = (len(y) - limit) // 2
        return y[start : start + limit]

    @staticmethod
    def estimate_bpm(
        y: np.ndarray,
        sr: int,
        preferred_min: float = 70.0,
        preferred_max: float = 190.0,
        *,
        max_analysis_seconds: float = DEFAULT_MAX_ANALYSIS_SECONDS,
        hop_length: int = DEFAULT_TEMPO_HOP_LENGTH,
        use_hpss: bool = DEFAULT_USE_HPSS,
    ) -> float | None:
        """Estimate BPM using windowed tempo analysis with octave folding.

        The signal is trimmed to a centred excerpt, scanned with overlapping
        windows, and the per-window tempo estimates are folded into the preferred
        band before being combined by weighted mode.

        Args:
            y: Audio signal, expected mono and normalised.
            sr: Sample rate of ``y``.
            preferred_min: Lower edge of the preferred tempo band.
            preferred_max: Upper edge of the preferred tempo band.
            max_analysis_seconds: Cap on how much audio is analysed.
            hop_length: Onset envelope hop, in samples. Smaller values raise tempo
                resolution at the cost of more onset/tempo computation.
            use_hpss: Apply harmonic/percussive separation first. Costly, and off
                by default; enable for material where the beat is masked by
                sustained harmonic content.

        Returns:
            Estimated tempo in BPM rounded to 0.1, or None if no reliable estimate
            could be formed.
        """
        if y is None or y.size == 0:
            return None

        # 1) Trim to a representative excerpt so cost does not scale with duration
        y = Predictor._centre_excerpt(y, sr, max_analysis_seconds)

        # 2) Optionally emphasize percussive content
        y_perc = librosa.effects.hpss(y)[1] if use_hpss else y

        # 3) Slide over windows, estimate tempo per window. Clips shorter than the
        #    nominal window are analysed whole rather than skipped outright.
        win = int(DEFAULT_TEMPO_WINDOW_SECONDS * sr)
        hop = int(DEFAULT_TEMPO_STRIDE_SECONDS * sr)
        if len(y_perc) < win:
            if len(y_perc) < MIN_TEMPO_WINDOW_SECONDS * sr:
                return None
            win = len(y_perc)
        min_segment = win // 2
        bpms, weights = [], []

        for start in range(0, max(1, len(y_perc) - win + 1), hop):
            seg = y_perc[start : start + win]
            if seg.size < min_segment:
                continue

            oenv = librosa.onset.onset_strength(y=seg, sr=sr, hop_length=hop_length, aggregate=np.median)
            if oenv.size < 8 or not np.isfinite(oenv).all():
                continue

            # Skip windows with no onset energy. Silence still produces a finite
            # (all-zero) envelope, and a zero-weighted histogram would otherwise
            # degenerate to its first bin and report a fabricated tempo.
            weight = float(np.mean(oenv))
            if not np.isfinite(weight) or weight <= MIN_ONSET_ENERGY:
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
            weights.append(weight)

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
        weight_arr = np.array(weights, dtype=float)

        # 4) Weighted mode via histogram, then refine via weighted average near the mode
        bins = np.arange(preferred_min, preferred_max + 0.5, 0.5)
        hist, edges = np.histogram(bpms_folded, bins=bins, weights=weight_arr)
        idx = int(np.argmax(hist))
        bpm_mode = 0.5 * (edges[idx] + edges[idx + 1])

        mask = np.abs(bpms_folded - bpm_mode) <= 2.0
        if np.any(mask):
            bpm_refined = float(np.average(bpms_folded[mask], weights=weight_arr[mask]))
        else:
            bpm_refined = float(bpm_mode)

        # Snap to 0.1 BPM to reduce jitter
        return round(bpm_refined, 1)
