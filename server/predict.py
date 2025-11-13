"""GenreFlow music genre predictor utilities.

This module provides a simple audio genre classification system that:
1. Loads and prepares audio files (normalizing, resampling, splitting)
2. Extracts simple features from each window of audio
3. Produces a probability-like prediction for each window and averages them
4. Returns the top predicted genres

Note: Currently uses a heuristic model. Will be replaced with ONNX/TFLite later.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import librosa
import numpy as np
import numpy.typing as npt
import soundfile as sf

from server.schemas import GenrePrediction, PredictionResult
from server.utils_audio import estimate_bpm

if TYPE_CHECKING:
    from pathlib import Path

# Configure logging
logger = logging.getLogger(__name__)

# Constants
GENRES = ["techno", "house", "rock", "hiphop", "jazz", "classical"]
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

    def _windows(
        self, y: npt.NDArray[np.float32], length_s: float = DEFAULT_WINDOW_SIZE
    ) -> list[npt.NDArray[np.float32]]:
        """Split audio into fixed-length windows.

        Args:
            y: Input audio signal
            length_s: Window length in seconds

        Returns:
            List of audio windows as numpy arrays
        """
        win_samples = int(length_s * self.sr)

        # Pad short clips to ensure at least one window
        if len(y) < win_samples:
            logger.debug(f"Padding audio from {len(y)} to {win_samples} samples")
            pad_length = win_samples - len(y)
            y = np.pad(y, (0, pad_length))

        # Extract windows with no overlap
        windows = [
            y[i : i + win_samples]
            for i in range(0, len(y), win_samples)
            if i + win_samples <= len(y)
        ]

        logger.debug(f"Split audio into {len(windows)} windows of {length_s}s each")
        return windows

    def _heuristic_window_prediction(self, w: npt.NDArray[np.float32]) -> npt.NDArray[np.float32]:
        """Generate probability scores for an audio window using simple heuristics.

        Args:
            w: Audio window as numpy array (float32), shape (n,)

        Returns:
            Probability distribution over genres, dtype float32, shape ``(len(GENRES),)``.

        Note:
            Placeholder using simple audio features; to be replaced by model inference.
        """
        # Ensure we always have something to return if an exception occurs early
        tempo: float = float("nan")

        try:
            # --- Feature extraction ---
            sc = float(librosa.feature.spectral_centroid(y=w, sr=self.sr).mean())
            zcr = float(librosa.feature.zero_crossing_rate(w).mean())
            tempo_est, _ = librosa.beat.beat_track(y=w, sr=self.sr)
            tempo = float(tempo_est)

            # --- Normalization (simple scalings/heuristics) ---
            sc_norm = sc / 5000.0  # brightness
            zcr_norm = zcr / 0.2  # percussiveness
            tempo_norm = tempo / 180.0  # speed

            # --- Pseudo-probabilities from features ---
            raw = np.array(
                [
                    0.6 * tempo_norm + 0.4 * sc_norm,  # electronic
                    0.5 * zcr_norm + 0.5 * sc_norm,  # rock
                    0.6 * zcr_norm + 0.4 * tempo_norm,  # hiphop
                    0.5 * (1.0 - sc_norm) + 0.3 * zcr_norm,  # jazz
                    0.8 * (1.0 - zcr_norm) + 0.2 * (1.0 - tempo_norm),  # classical
                ],
                dtype=np.float32,
            )

            # --- Normalize to probabilities ---
            raw = np.clip(raw, 0.001, None)
            probs = (raw / float(raw.sum())).astype(np.float32, copy=False)

            return probs

        except Exception as e:
            logger.error(f"Failed to predict window: {e}")
            fallback = np.ones(len(GENRES), dtype=np.float32) / float(len(GENRES))
            return fallback

    def _get_song_bpm(self, y: npt.NDArray[np.float32]) -> float:
        """Estimate the BPM of the entire audio clip.

        Args:
            y: Input audio signal

        Returns:
            Estimated BPM as a float
        """
        try:
            tempo, _ = librosa.beat.beat_track(y=y, sr=self.sr)
            return float(tempo)
        except Exception as e:
            logger.error(f"Failed to estimate BPM: {e}")
            return float("nan")

    def predict_bytes(self, audio_bytes: bytes, top_k: int = 3) -> PredictionResult:
        """Predict genres from audio file bytes.

        Args:
            audio_bytes: Raw audio file bytes
            top_k: Number of top predictions to return (default: 3)

        Returns:
            PredictionResult containing top-k predictions

        Raises:
            ValueError: If audio cannot be loaded or processed
        """
        # Load and window audio
        y, _ = self._load_audio(audio_bytes)
        # tempo = self._get_song_bpm(y)
        bpm = estimate_bpm(y, sr=self.sr)
        windows = self._windows(y, length_s=self.config.window_size)

        # Get predictions for each window
        win_probs = [self._heuristic_window_prediction(w) for w in windows]
        mean_probs = np.mean(win_probs, axis=0)

        # Sort and format predictions
        top_idx = np.argsort(mean_probs)[::-1][:top_k]

        return PredictionResult(
            top_k=[GenrePrediction(label=GENRES[i], score=float(mean_probs[i])) for i in top_idx],
            bpm=bpm,
            # per_window=[
            #     [
            #         GenrePrediction(
            #             label=GENRES[i],
            #             score=float(p[i])
            #         )
            #         for i in np.argsort(p)[::-1][:top_k]
            #     ]
            #     for p in win_probs
            # ]
        )
