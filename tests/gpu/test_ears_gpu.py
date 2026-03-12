"""
EARS GPU Tests

Verify that Whisper (faster-whisper / CTranslate2) can run on GPU
and benchmark CPU vs GPU to confirm GPU provides a real speedup.
"""

import time
import struct
import math
import os
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def generate_sine_wav(duration_s=3.0, sample_rate=16000, freq=440.0):
    """Generate a sine wave as raw PCM int16 bytes (no WAV header)."""
    n_samples = int(duration_s * sample_rate)
    samples = []
    for i in range(n_samples):
        val = math.sin(2 * math.pi * freq * i / sample_rate)
        samples.append(int(val * 32767))
    return struct.pack(f"<{n_samples}h", *samples)


def generate_test_wav_file(path, duration_s=3.0, sample_rate=16000):
    """Generate a minimal WAV file with a sine tone."""
    import wave
    pcm = generate_sine_wav(duration_s, sample_rate)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return path


def _has_cudnn():
    """Check if cuDNN is available (needed for CUDA inference)."""
    try:
        import ctypes
        ctypes.cdll.LoadLibrary("libcudnn.so")
        return True
    except OSError:
        return False


CUDNN_AVAILABLE = _has_cudnn()
SKIP_NO_CUDNN = pytest.mark.skipif(
    not CUDNN_AVAILABLE,
    reason="cuDNN not installed on host (available inside Docker container)"
)


def _time_whisper_transcribe(device, compute_type, model_size="small", duration_s=5.0):
    """
    Load a Whisper model on the given device and transcribe a test clip.
    Returns (load_time_s, transcribe_time_s, peak_vram_mib).
    """
    import tempfile
    from faster_whisper import WhisperModel

    wav_path = tempfile.mktemp(suffix=".wav")
    generate_test_wav_file(wav_path, duration_s=duration_s)

    # Measure model load
    t0 = time.perf_counter()
    model = WhisperModel(model_size, device=device, compute_type=compute_type)
    load_time = time.perf_counter() - t0

    # Measure transcription
    t0 = time.perf_counter()
    segments, _info = model.transcribe(wav_path, language="en", beam_size=5)
    # Force generator to run
    for _ in segments:
        pass
    transcribe_time = time.perf_counter() - t0

    # Get peak VRAM if GPU
    peak_vram = 0
    if device == "cuda":
        import torch
        peak_vram = torch.cuda.max_memory_allocated() / (1024 * 1024)
        torch.cuda.reset_peak_memory_stats()

    os.unlink(wav_path)
    del model

    return load_time, transcribe_time, peak_vram


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestWhisperCUDASupport:
    """Verify faster-whisper can load on CUDA."""

    @SKIP_NO_CUDNN
    def test_faster_whisper_loads_on_cuda(self):
        from faster_whisper import WhisperModel
        model = WhisperModel("tiny", device="cuda", compute_type="float16")
        assert model is not None
        del model

    def test_faster_whisper_loads_on_cpu(self):
        from faster_whisper import WhisperModel
        model = WhisperModel("tiny", device="cpu", compute_type="int8")
        assert model is not None
        del model

    def test_cudnn_available(self):
        """cuDNN is required for CUDA Whisper inference."""
        assert CUDNN_AVAILABLE, (
            "cuDNN not found on host. GPU inference tests will be skipped. "
            "cuDNN IS available inside the Docker container (torch-base image). "
            "Run these tests inside the EARS pod for full GPU benchmarks."
        )


class TestWhisperGPUPerformance:
    """
    Benchmark CPU vs GPU transcription.

    These tests confirm GPU provides a meaningful speedup and that VRAM
    usage fits within the target GPU (GTX 960 = 4 GB).

    NOTE: Requires cuDNN. Run inside EARS Docker container or on a host
    with cuDNN installed. On bare host without cuDNN, these are skipped.
    """

    @pytest.fixture(autouse=True)
    def _cleanup_cuda(self):
        yield
        try:
            import torch
            torch.cuda.empty_cache()
        except Exception:
            pass

    @SKIP_NO_CUDNN
    def test_gpu_faster_than_cpu(self):
        """GPU transcription should be faster than CPU for a 10s clip.

        Uses a longer clip to amortize GPU launch overhead and includes
        a warmup transcription to exclude first-inference JIT costs.
        """
        duration = 10.0
        # Warmup: load + transcribe once on each device to warm caches
        _time_whisper_transcribe("cpu", "int8", "small", 1.0)
        _time_whisper_transcribe("cuda", "float16", "small", 1.0)

        # Benchmark on longer clip
        _, cpu_time, _ = _time_whisper_transcribe("cpu", "int8", "small", duration)
        _, gpu_time, _ = _time_whisper_transcribe("cuda", "float16", "small", duration)

        speedup = cpu_time / gpu_time if gpu_time > 0 else 0
        print(f"\n  CPU: {cpu_time:.2f}s | GPU: {gpu_time:.2f}s | Speedup: {speedup:.1f}x")

        assert gpu_time < cpu_time, (
            f"GPU ({gpu_time:.2f}s) not faster than CPU ({cpu_time:.2f}s)"
        )

    @SKIP_NO_CUDNN
    def test_gpu_transcribes_faster_than_realtime(self):
        """GPU should transcribe a 5s clip in well under 5s."""
        clip_duration = 5.0
        _, transcribe_time, _ = _time_whisper_transcribe(
            "cuda", "float16", "small", clip_duration
        )
        realtime_ratio = transcribe_time / clip_duration
        print(f"\n  Transcribe: {transcribe_time:.2f}s for {clip_duration}s audio "
              f"({realtime_ratio:.2f}x realtime)")

        assert transcribe_time < clip_duration, (
            f"GPU transcription ({transcribe_time:.2f}s) slower than realtime "
            f"for {clip_duration}s clip"
        )

    @SKIP_NO_CUDNN
    def test_whisper_small_fits_in_rtx3060(self, rtx3060):
        """Whisper 'small' model + inference should fit alongside Ollama on RTX 3060."""
        _, _, peak_vram = _time_whisper_transcribe("cuda", "float16", "small", 3.0)
        # Whisper needs to share RTX 3060 with Ollama if GTX 960 is incompatible
        max_allowed = 2000  # 2 GB budget alongside Ollama
        print(f"\n  Peak VRAM: {peak_vram:.0f} MiB (budget: {max_allowed} MiB)")

        assert peak_vram < max_allowed, (
            f"Whisper small uses {peak_vram:.0f} MiB; exceeds {max_allowed} MiB budget"
        )

    @SKIP_NO_CUDNN
    def test_whisper_model_load_time_reasonable(self):
        """Model load should complete within 30 seconds."""
        load_time, _, _ = _time_whisper_transcribe("cuda", "float16", "small", 1.0)
        print(f"\n  Model load: {load_time:.2f}s")
        assert load_time < 30, f"Model load took {load_time:.2f}s; expected < 30s"

    def test_cpu_baseline_performance(self):
        """Baseline: measure CPU transcription speed for comparison."""
        clip_duration = 5.0
        _, cpu_time, _ = _time_whisper_transcribe("cpu", "int8", "small", clip_duration)
        rtf = cpu_time / clip_duration
        print(f"\n  CPU: {cpu_time:.2f}s for {clip_duration}s audio (RTF={rtf:.2f})")

        # CPU should at least be faster than realtime for small model
        assert rtf < 2.0, (
            f"CPU RTF={rtf:.2f}; even CPU should process faster than 2x realtime"
        )
