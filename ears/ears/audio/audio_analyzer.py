"""
Audio analyzer for detecting defects in PCM audio chunks.

Analyzes incoming audio for common issues like:
- Silence or low volume
- Clipping/distortion
- DC offset
- Wrong chunk size
- Noise (no speech)
- Wrong byte order
"""

from dataclasses import dataclass
from typing import Optional

import numpy as np
from loguru import logger


# ------------------------------------------------------------------------------
# configuration
# ------------------------------------------------------------------------------

@dataclass
class AnalysisConfig:
    """Thresholds for defect detection."""
    sample_rate: int = 16000

    # Volume thresholds (RMS in 0-1 range after normalization)
    low_volume_threshold: float = 0.01      # ~-40 dB
    silence_threshold: float = 0.0001       # ~-80 dB

    # Clipping detection
    clipping_sample_ratio: float = 0.02     # >2% samples clipped = error

    # DC offset threshold (mean absolute deviation from zero)
    dc_offset_threshold: float = 0.1        # 10% of full scale

    # Chunk size bounds (in ms)
    chunk_min_ms: float = 50.0
    chunk_max_ms: float = 500.0

    # Noise detection (using zero-crossing rate)
    noise_zcr_threshold: float = 0.4        # High ZCR = likely noise

    # Sample rate detection (using spectral centroid in Hz)
    # Normal speech has spectral centroid ~1000-2500 Hz
    # When sample rate is wrong by 3x, centroid shifts by ~2-3x
    spectral_centroid_min_hz: float = 800.0   # Below this = likely playing too slow
    spectral_centroid_max_hz: float = 4000.0  # Above this = likely playing too fast

    # Truncation detection
    truncation_rms_threshold: float = 0.05    # If last chunk RMS > this, likely truncated


# ------------------------------------------------------------------------------
# metrics dataclass
# ------------------------------------------------------------------------------

@dataclass
class AudioMetrics:
    """Computed audio metrics for a chunk."""
    sample_count: int
    duration_ms: float
    rms: float                  # Root mean square (volume)
    peak: float                 # Maximum absolute sample value
    dc_offset: float            # Mean value (should be ~0)
    clipping_ratio: float       # Ratio of samples at max
    zero_crossing_rate: float   # For noise detection
    spectral_centroid: float    # Center of mass of frequency spectrum (Hz)


# ------------------------------------------------------------------------------
# defect dataclass
# ------------------------------------------------------------------------------

@dataclass
class Defect:
    """Individual audio defect detected."""
    code: str
    severity: str  # "warning" | "error"
    message: str
    value: Optional[float] = None
    threshold: Optional[float] = None


# ------------------------------------------------------------------------------
# audio analyzer
# ------------------------------------------------------------------------------

class AudioAnalyzer:
    """Analyzes PCM audio chunks for defects."""

    def __init__(self, config: Optional[AnalysisConfig] = None):
        self.config = config or AnalysisConfig()
        self._chunk_count = 0
        # Stream-level state for truncation detection
        self._last_rms = 0.0

    def analyze_chunk(self, audio_bytes: bytes) -> tuple[AudioMetrics, list[Defect]]:
        """
        Analyze a single audio chunk for defects.

        Args:
            audio_bytes: Raw PCM Int16 audio data (little-endian)

        Returns:
            Tuple of (metrics, defects)
        """
        self._chunk_count += 1

        # Handle odd byte count
        if len(audio_bytes) % 2 != 0:
            audio_bytes = audio_bytes[:-1]

        # Handle empty chunk
        if len(audio_bytes) == 0:
            return self._empty_metrics(), [Defect(
                code="empty_chunk",
                severity="error",
                message="Received empty audio chunk"
            )]

        # Parse as Int16 little-endian (expected format)
        samples = np.frombuffer(audio_bytes, dtype=np.int16)
        samples_float = samples.astype(np.float32) / 32768.0

        metrics = self._compute_metrics(samples_float, len(samples))
        defects = self._detect_defects(metrics, samples)

        # Track RMS for truncation detection
        self._last_rms = metrics.rms

        return metrics, defects

    def _empty_metrics(self) -> AudioMetrics:
        """Return metrics for an empty chunk."""
        return AudioMetrics(
            sample_count=0,
            duration_ms=0.0,
            rms=0.0,
            peak=0.0,
            dc_offset=0.0,
            clipping_ratio=0.0,
            zero_crossing_rate=0.0,
            spectral_centroid=0.0,
        )

    def _compute_metrics(self, samples: np.ndarray, count: int) -> AudioMetrics:
        """Compute audio metrics from normalized samples (-1 to 1 range)."""
        return AudioMetrics(
            sample_count=count,
            duration_ms=count / self.config.sample_rate * 1000,
            rms=float(np.sqrt(np.mean(samples ** 2))),
            peak=float(np.max(np.abs(samples))),
            dc_offset=float(np.mean(samples)),
            clipping_ratio=float(np.sum(np.abs(samples) > 0.99) / max(len(samples), 1)),
            zero_crossing_rate=self._compute_zcr(samples),
            spectral_centroid=self._compute_spectral_centroid(samples),
        )

    def _compute_zcr(self, samples: np.ndarray) -> float:
        """Compute zero-crossing rate."""
        if len(samples) < 2:
            return 0.0
        signs = np.sign(samples)
        sign_changes = np.sum(signs[1:] != signs[:-1])
        return float(sign_changes / (len(samples) - 1))

    def _compute_spectral_centroid(self, samples: np.ndarray) -> float:
        """
        Compute spectral centroid (center of mass of frequency spectrum).

        Normal speech has centroid ~1000-3000 Hz.
        Too low = audio playing too slow (wrong sample rate).
        Too high = audio playing too fast (wrong sample rate).
        """
        if len(samples) < 64:
            return 0.0

        # Compute FFT magnitude spectrum
        fft_magnitude = np.abs(np.fft.rfft(samples))

        # Compute corresponding frequencies
        freqs = np.fft.rfftfreq(len(samples), 1.0 / self.config.sample_rate)

        # Compute spectral centroid (weighted average of frequencies)
        total_magnitude = np.sum(fft_magnitude)
        if total_magnitude < 1e-10:
            return 0.0

        centroid = np.sum(freqs * fft_magnitude) / total_magnitude
        return float(centroid)

    def _detect_defects(self, metrics: AudioMetrics, raw_samples: np.ndarray) -> list[Defect]:
        """Detect audio defects based on metrics."""
        defects = []

        # 1. Silence detection
        if metrics.rms < self.config.silence_threshold:
            defects.append(Defect(
                code="silence",
                severity="error",
                message="Audio is silent (all samples near zero)",
                value=metrics.rms,
                threshold=self.config.silence_threshold,
            ))
        # 2. Low volume detection (only if not silence)
        elif metrics.rms < self.config.low_volume_threshold:
            defects.append(Defect(
                code="low_volume",
                severity="warning",
                message=f"Audio volume is very low (RMS: {metrics.rms:.4f})",
                value=metrics.rms,
                threshold=self.config.low_volume_threshold,
            ))

        # 3. Clipping detection
        if metrics.clipping_ratio > self.config.clipping_sample_ratio:
            defects.append(Defect(
                code="clipping",
                severity="error",
                message=f"Audio is clipping ({metrics.clipping_ratio*100:.1f}% samples at max)",
                value=metrics.clipping_ratio,
                threshold=self.config.clipping_sample_ratio,
            ))

        # 4. DC offset detection
        if abs(metrics.dc_offset) > self.config.dc_offset_threshold:
            defects.append(Defect(
                code="dc_offset",
                severity="warning",
                message=f"DC offset detected (mean: {metrics.dc_offset:.3f})",
                value=metrics.dc_offset,
                threshold=self.config.dc_offset_threshold,
            ))

        # 5. Wrong chunk size detection
        if metrics.duration_ms < self.config.chunk_min_ms:
            defects.append(Defect(
                code="wrong_chunk_size",
                severity="warning",
                message=f"Chunk too small ({metrics.duration_ms:.0f}ms < {self.config.chunk_min_ms}ms)",
                value=metrics.duration_ms,
                threshold=self.config.chunk_min_ms,
            ))
        elif metrics.duration_ms > self.config.chunk_max_ms:
            defects.append(Defect(
                code="wrong_chunk_size",
                severity="warning",
                message=f"Chunk too large ({metrics.duration_ms:.0f}ms > {self.config.chunk_max_ms}ms)",
                value=metrics.duration_ms,
                threshold=self.config.chunk_max_ms,
            ))

        # 6. Noise detection (high ZCR with reasonable volume)
        if metrics.zero_crossing_rate > self.config.noise_zcr_threshold and metrics.rms > 0.01:
            defects.append(Defect(
                code="noise_only",
                severity="warning",
                message=f"Audio appears to be noise (ZCR: {metrics.zero_crossing_rate:.2f})",
                value=metrics.zero_crossing_rate,
                threshold=self.config.noise_zcr_threshold,
            ))

        # 7. Wrong byte order detection
        if self._detect_wrong_byte_order(raw_samples):
            defects.append(Defect(
                code="wrong_byte_order",
                severity="error",
                message="Audio may have wrong byte order (sounds like static)",
                value=None,
                threshold=None,
            ))

        # 8. Wrong sample rate detection (only if we have enough signal)
        if metrics.rms > 0.01 and metrics.spectral_centroid > 0:
            if metrics.spectral_centroid < self.config.spectral_centroid_min_hz:
                defects.append(Defect(
                    code="wrong_sample_rate",
                    severity="warning",
                    message=f"Audio may have wrong sample rate - frequencies too low "
                            f"(centroid: {metrics.spectral_centroid:.0f} Hz)",
                    value=metrics.spectral_centroid,
                    threshold=self.config.spectral_centroid_min_hz,
                ))
            elif metrics.spectral_centroid > self.config.spectral_centroid_max_hz:
                defects.append(Defect(
                    code="wrong_sample_rate",
                    severity="warning",
                    message=f"Audio may have wrong sample rate - frequencies too high "
                            f"(centroid: {metrics.spectral_centroid:.0f} Hz)",
                    value=metrics.spectral_centroid,
                    threshold=self.config.spectral_centroid_max_hz,
                ))

        return defects

    def _detect_wrong_byte_order(self, samples: np.ndarray) -> bool:
        """
        Detect if audio bytes are in wrong order.

        Compare ZCR of original vs byte-swapped samples.
        If swapped version has much lower ZCR, likely wrong order.
        """
        if len(samples) < 100:
            return False

        original_float = samples.astype(np.float32) / 32768.0
        original_zcr = self._compute_zcr(original_float)

        # Only check if original looks noisy
        if original_zcr < 0.3:
            return False

        # Byte-swap and compare
        swapped = samples.byteswap()
        swapped_float = swapped.astype(np.float32) / 32768.0
        swapped_zcr = self._compute_zcr(swapped_float)

        # If swapped version has much lower ZCR, bytes are probably wrong
        return swapped_zcr < original_zcr * 0.5

    def finalize(self) -> list[Defect]:
        """
        Called when stream ends. Detects stream-level defects.

        Returns:
            List of stream-level defects (e.g., truncation).
        """
        defects = []

        # If last chunk had significant audio (not silence), likely truncated
        if self._last_rms > self.config.truncation_rms_threshold:
            defects.append(Defect(
                code="truncated",
                severity="warning",
                message=f"Audio stream ended abruptly (RMS: {self._last_rms:.3f}) - may be truncated",
                value=self._last_rms,
                threshold=self.config.truncation_rms_threshold,
            ))

        return defects

    def reset(self):
        """Reset analyzer state."""
        self._chunk_count = 0
        self._last_rms = 0.0


# ------------------------------------------------------------------------------
# factory function
# ------------------------------------------------------------------------------

def create_audio_analyzer(config: Optional[AnalysisConfig] = None) -> AudioAnalyzer:
    """Create an AudioAnalyzer instance."""
    return AudioAnalyzer(config)
