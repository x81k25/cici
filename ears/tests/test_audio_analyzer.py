"""Unit tests for AudioAnalyzer defect detection."""

import numpy as np
import pytest

from ears.audio.audio_analyzer import AudioAnalyzer, AnalysisConfig


# ------------------------------------------------------------------------------
# fixtures
# ------------------------------------------------------------------------------

@pytest.fixture
def analyzer():
    """Create a default AudioAnalyzer."""
    return AudioAnalyzer()


def make_pcm(samples: np.ndarray) -> bytes:
    """Convert float samples (-1 to 1) to PCM Int16 bytes."""
    int_samples = (samples * 32767).astype(np.int16)
    return int_samples.tobytes()


# ------------------------------------------------------------------------------
# silence and volume tests
# ------------------------------------------------------------------------------

class TestSilenceDetection:
    """Tests for silence detection."""

    def test_detect_silence(self, analyzer):
        """Test that all-zero audio is detected as silence."""
        samples = np.zeros(1600, dtype=np.float32)
        audio_bytes = make_pcm(samples)

        metrics, defects = analyzer.analyze_chunk(audio_bytes)

        assert any(d.code == "silence" for d in defects)
        assert metrics.rms < 0.001

    def test_detect_low_volume(self, analyzer):
        """Test that very quiet audio is detected as low volume."""
        # 440Hz tone at 0.5% amplitude (very quiet)
        t = np.linspace(0, 0.1, 1600, dtype=np.float32)
        samples = np.sin(2 * np.pi * 440 * t) * 0.005
        audio_bytes = make_pcm(samples)

        metrics, defects = analyzer.analyze_chunk(audio_bytes)

        assert any(d.code == "low_volume" for d in defects)
        assert metrics.rms < 0.01


# ------------------------------------------------------------------------------
# clipping tests
# ------------------------------------------------------------------------------

class TestClippingDetection:
    """Tests for clipping/distortion detection."""

    def test_detect_clipping(self, analyzer):
        """Test that over-driven audio with clipping is detected."""
        # Over-driven sine wave (clips at ±1.0)
        t = np.linspace(0, 0.1, 1600, dtype=np.float32)
        samples = np.sin(2 * np.pi * 440 * t) * 2.0  # 2x amplitude
        samples = np.clip(samples, -1.0, 1.0)
        audio_bytes = make_pcm(samples)

        metrics, defects = analyzer.analyze_chunk(audio_bytes)

        assert any(d.code == "clipping" for d in defects)
        assert metrics.clipping_ratio > 0.01


# ------------------------------------------------------------------------------
# DC offset tests
# ------------------------------------------------------------------------------

class TestDCOffsetDetection:
    """Tests for DC offset detection."""

    def test_detect_dc_offset(self, analyzer):
        """Test that audio with large DC offset is detected."""
        # Sine wave with +50% DC offset
        t = np.linspace(0, 0.1, 1600, dtype=np.float32)
        samples = np.sin(2 * np.pi * 440 * t) * 0.3 + 0.5
        # Clip to valid range
        samples = np.clip(samples, -1.0, 1.0)
        audio_bytes = make_pcm(samples)

        metrics, defects = analyzer.analyze_chunk(audio_bytes)

        assert any(d.code == "dc_offset" for d in defects)
        assert abs(metrics.dc_offset) > 0.1


# ------------------------------------------------------------------------------
# chunk size tests
# ------------------------------------------------------------------------------

class TestChunkSizeDetection:
    """Tests for wrong chunk size detection."""

    def test_detect_chunk_too_small(self, analyzer):
        """Test that chunks <50ms are flagged."""
        # 25ms at 16kHz = 400 samples
        t = np.linspace(0, 0.025, 400, dtype=np.float32)
        samples = np.sin(2 * np.pi * 440 * t) * 0.5
        audio_bytes = make_pcm(samples)

        metrics, defects = analyzer.analyze_chunk(audio_bytes)

        assert any(d.code == "wrong_chunk_size" for d in defects)
        assert metrics.duration_ms < 50

    def test_detect_chunk_too_large(self, analyzer):
        """Test that chunks >500ms are flagged."""
        # 1000ms at 16kHz = 16000 samples
        t = np.linspace(0, 1.0, 16000, dtype=np.float32)
        samples = np.sin(2 * np.pi * 440 * t) * 0.5
        audio_bytes = make_pcm(samples)

        metrics, defects = analyzer.analyze_chunk(audio_bytes)

        assert any(d.code == "wrong_chunk_size" for d in defects)
        assert metrics.duration_ms > 500


# ------------------------------------------------------------------------------
# noise tests
# ------------------------------------------------------------------------------

class TestNoiseDetection:
    """Tests for noise detection."""

    def test_detect_noise(self, analyzer):
        """Test that random noise is detected."""
        np.random.seed(42)
        samples = (np.random.random(1600) * 2 - 1).astype(np.float32) * 0.5
        audio_bytes = make_pcm(samples)

        metrics, defects = analyzer.analyze_chunk(audio_bytes)

        assert any(d.code == "noise_only" for d in defects)
        assert metrics.zero_crossing_rate > 0.3


# ------------------------------------------------------------------------------
# byte order tests
# ------------------------------------------------------------------------------

class TestByteOrderDetection:
    """Tests for wrong byte order detection."""

    def test_detect_wrong_byte_order(self, analyzer):
        """Test that byte-swapped audio is detected."""
        # Create normal audio
        t = np.linspace(0, 0.1, 1600, dtype=np.float32)
        samples = np.sin(2 * np.pi * 440 * t) * 0.5
        int_samples = (samples * 32767).astype(np.int16)

        # Byte-swap to simulate wrong endianness
        swapped = int_samples.byteswap()
        audio_bytes = swapped.tobytes()

        metrics, defects = analyzer.analyze_chunk(audio_bytes)

        assert any(d.code == "wrong_byte_order" for d in defects)


# ------------------------------------------------------------------------------
# clean audio tests
# ------------------------------------------------------------------------------

# ------------------------------------------------------------------------------
# edge cases
# ------------------------------------------------------------------------------

class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_chunk(self, analyzer):
        """Test handling of empty audio chunk."""
        audio_bytes = b""

        metrics, defects = analyzer.analyze_chunk(audio_bytes)

        assert any(d.code == "empty_chunk" for d in defects)
        assert metrics.sample_count == 0

    def test_odd_byte_count(self, analyzer):
        """Test handling of odd byte count (truncated sample)."""
        # 1601 bytes = 800 samples + 1 extra byte
        t = np.linspace(0, 0.05, 800, dtype=np.float32)
        samples = np.sin(2 * np.pi * 440 * t) * 0.3
        audio_bytes = make_pcm(samples) + b"\x00"  # Add extra byte

        metrics, defects = analyzer.analyze_chunk(audio_bytes)

        # Should handle gracefully by trimming the extra byte
        assert metrics.sample_count == 800

    def test_reset(self, analyzer):
        """Test analyzer reset."""
        samples = np.zeros(1600, dtype=np.float32)
        audio_bytes = make_pcm(samples)

        analyzer.analyze_chunk(audio_bytes)
        analyzer.analyze_chunk(audio_bytes)
        assert analyzer._chunk_count == 2

        analyzer.reset()
        assert analyzer._chunk_count == 0


# ------------------------------------------------------------------------------
# wrong sample rate tests
# ------------------------------------------------------------------------------

class TestWrongSampleRateDetection:
    """Tests for wrong sample rate detection via spectral centroid."""

    def test_detect_sample_rate_too_slow(self, analyzer):
        """Audio with very low frequencies suggests wrong sample rate (too slow)."""
        # Create a very low frequency tone (100Hz) - below normal speech range
        # This simulates audio recorded at 48kHz being played at 16kHz (3x slower)
        t = np.linspace(0, 0.1, 1600, dtype=np.float32)
        samples = np.sin(2 * np.pi * 100 * t) * 0.5  # 100Hz tone
        audio_bytes = make_pcm(samples)

        metrics, defects = analyzer.analyze_chunk(audio_bytes)

        assert metrics.spectral_centroid < 500  # Very low centroid
        assert any(d.code == "wrong_sample_rate" for d in defects)

    def test_detect_sample_rate_too_fast(self, analyzer):
        """Audio with very high frequencies suggests wrong sample rate (too fast)."""
        # Create a very high frequency tone (6000Hz) - above normal speech range
        # This simulates audio recorded at 16kHz being played at 48kHz (3x faster)
        t = np.linspace(0, 0.1, 1600, dtype=np.float32)
        samples = np.sin(2 * np.pi * 6000 * t) * 0.5  # 6000Hz tone
        audio_bytes = make_pcm(samples)

        metrics, defects = analyzer.analyze_chunk(audio_bytes)

        assert metrics.spectral_centroid > 4000  # Very high centroid
        assert any(d.code == "wrong_sample_rate" for d in defects)

    def test_normal_sample_rate_no_defect(self, analyzer):
        """Normal speech-like frequencies don't trigger wrong sample rate."""
        # Create a tone in normal speech range (1000Hz)
        t = np.linspace(0, 0.1, 1600, dtype=np.float32)
        samples = np.sin(2 * np.pi * 1000 * t) * 0.3  # 1000Hz tone
        audio_bytes = make_pcm(samples)

        metrics, defects = analyzer.analyze_chunk(audio_bytes)

        assert 500 < metrics.spectral_centroid < 4000
        assert not any(d.code == "wrong_sample_rate" for d in defects)


# ------------------------------------------------------------------------------
# truncated stream tests
# ------------------------------------------------------------------------------

class TestTruncatedDetection:
    """Tests for truncated stream detection via finalize()."""

    def test_detect_truncated_during_speech(self, analyzer):
        """Stream ending during active audio is flagged as truncated."""
        # Send a chunk with significant audio (high RMS)
        t = np.linspace(0, 0.1, 1600, dtype=np.float32)
        samples = np.sin(2 * np.pi * 440 * t) * 0.5  # 50% amplitude
        audio_bytes = make_pcm(samples)

        analyzer.analyze_chunk(audio_bytes)

        # Finalize should detect truncation (last chunk had high RMS)
        final_defects = analyzer.finalize()

        assert any(d.code == "truncated" for d in final_defects)

    def test_no_truncation_after_silence(self, analyzer):
        """Stream ending after silence is not flagged as truncated."""
        # First send some audio
        t = np.linspace(0, 0.1, 1600, dtype=np.float32)
        samples = np.sin(2 * np.pi * 440 * t) * 0.5
        audio_bytes = make_pcm(samples)
        analyzer.analyze_chunk(audio_bytes)

        # Then send silence (low RMS)
        silence = np.zeros(1600, dtype=np.float32)
        silence_bytes = make_pcm(silence)
        analyzer.analyze_chunk(silence_bytes)

        # Finalize should NOT detect truncation (last chunk was silence)
        final_defects = analyzer.finalize()

        assert not any(d.code == "truncated" for d in final_defects)

    def test_finalize_returns_empty_after_reset(self, analyzer):
        """After reset, finalize returns no defects."""
        # Send audio
        t = np.linspace(0, 0.1, 1600, dtype=np.float32)
        samples = np.sin(2 * np.pi * 440 * t) * 0.5
        audio_bytes = make_pcm(samples)
        analyzer.analyze_chunk(audio_bytes)

        # Reset clears state
        analyzer.reset()

        # Finalize should return empty (no state to analyze)
        final_defects = analyzer.finalize()

        assert len(final_defects) == 0
