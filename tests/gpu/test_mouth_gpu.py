"""
MOUTH GPU Tests

Verify that Piper TTS can run on GPU via ONNX Runtime's CUDAExecutionProvider
and benchmark CPU vs GPU synthesis.

NOTE: Piper GPU requires:
  1. onnxruntime-gpu (not plain onnxruntime)
  2. PiperVoice.load(..., use_cuda=True)
  3. CUDA-capable Docker image

If onnxruntime-gpu is not installed, GPU tests will be skipped with
a clear message indicating what needs to change.
"""

import io
import os
import time
import wave
import glob
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_piper_model():
    """Find a Piper ONNX model file."""
    search_paths = [
        "/models/*.onnx",
        "mouth/models/*.onnx",
        "../mouth/models/*.onnx",
    ]
    for pattern in search_paths:
        matches = glob.glob(pattern)
        if matches:
            return matches[0]
    return None


def _has_cuda_provider():
    """Check if ONNX Runtime has CUDAExecutionProvider."""
    try:
        import onnxruntime
        return "CUDAExecutionProvider" in onnxruntime.get_available_providers()
    except ImportError:
        return False


def _time_piper_synthesis(use_cuda, text="The quick brown fox jumps over the lazy dog.", repeats=5):
    """
    Load Piper model and synthesize text.
    Returns (load_time_s, avg_synthesis_time_s, peak_vram_mib).
    """
    from piper import PiperVoice

    model_path = _find_piper_model()
    if model_path is None:
        pytest.skip("No Piper ONNX model found")

    config_path = model_path + ".json"
    if not os.path.exists(config_path):
        pytest.skip(f"No config file at {config_path}")

    if use_cuda:
        import torch
        torch.cuda.reset_peak_memory_stats()

    # Measure model load
    t0 = time.perf_counter()
    voice = PiperVoice.load(model_path, config_path=config_path, use_cuda=use_cuda)
    load_time = time.perf_counter() - t0

    # Warmup
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        voice.synthesize_wav("warmup", wf)

    # Measure synthesis (average over repeats)
    times = []
    for _ in range(repeats):
        buf = io.BytesIO()
        t0 = time.perf_counter()
        with wave.open(buf, "wb") as wf:
            voice.synthesize_wav(text, wf)
        times.append(time.perf_counter() - t0)

    avg_time = sum(times) / len(times)

    # Get audio duration for RTF calculation
    buf.seek(0)
    with wave.open(buf, "rb") as wf:
        n_frames = wf.getnframes()
        rate = wf.getframerate()
        audio_duration = n_frames / rate

    peak_vram = 0
    if use_cuda:
        import torch
        peak_vram = torch.cuda.max_memory_allocated() / (1024 * 1024)
        torch.cuda.reset_peak_memory_stats()

    del voice
    return load_time, avg_time, audio_duration, peak_vram


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPiperCUDASupport:
    """Check if the environment supports Piper on GPU."""

    def test_onnxruntime_gpu_installed(self):
        """onnxruntime-gpu must be installed for MOUTH GPU support."""
        import onnxruntime
        providers = onnxruntime.get_available_providers()
        assert "CUDAExecutionProvider" in providers, (
            f"CUDAExecutionProvider missing. Available: {providers}. "
            "ACTION: Replace 'onnxruntime' with 'onnxruntime-gpu' in "
            "mouth/pyproject.toml and rebuild the Docker image with a "
            "CUDA base image."
        )

    def test_piper_model_exists(self):
        model = _find_piper_model()
        assert model is not None, (
            "No Piper .onnx model found in /models/ or mouth/models/"
        )

    @pytest.mark.skipif(not _has_cuda_provider(), reason="onnxruntime-gpu not installed")
    def test_piper_loads_with_cuda(self):
        from piper import PiperVoice
        model_path = _find_piper_model()
        if model_path is None:
            pytest.skip("No model")
        config_path = model_path + ".json"
        voice = PiperVoice.load(model_path, config_path=config_path, use_cuda=True)
        assert voice is not None
        del voice


class TestPiperCPUBaseline:
    """Baseline CPU performance -- always runs."""

    def test_cpu_synthesis_speed(self):
        """Measure CPU synthesis and report Real-Time Factor."""
        load_time, avg_time, audio_dur, _ = _time_piper_synthesis(use_cuda=False)
        rtf = avg_time / audio_dur if audio_dur > 0 else float("inf")
        print(f"\n  CPU: load={load_time:.2f}s  synth={avg_time:.3f}s  "
              f"audio={audio_dur:.2f}s  RTF={rtf:.3f}")

        # Piper on CPU should still be faster than realtime
        assert rtf < 1.0, (
            f"CPU synthesis RTF={rtf:.3f} (>1.0 means slower than realtime)"
        )


@pytest.mark.skipif(not _has_cuda_provider(), reason="onnxruntime-gpu not installed")
class TestPiperGPUPerformance:
    """GPU performance tests -- only run if onnxruntime-gpu is available."""

    @pytest.fixture(autouse=True)
    def _cleanup_cuda(self):
        yield
        try:
            import torch
            torch.cuda.empty_cache()
        except Exception:
            pass

    def test_gpu_faster_than_cpu(self):
        """GPU synthesis should be faster than CPU."""
        _, cpu_time, _, _ = _time_piper_synthesis(use_cuda=False)
        _, gpu_time, _, _ = _time_piper_synthesis(use_cuda=True)

        speedup = cpu_time / gpu_time if gpu_time > 0 else 0
        print(f"\n  CPU: {cpu_time:.3f}s | GPU: {gpu_time:.3f}s | Speedup: {speedup:.1f}x")

        assert gpu_time < cpu_time, (
            f"GPU ({gpu_time:.3f}s) not faster than CPU ({cpu_time:.3f}s)"
        )

    def test_gpu_synthesis_rtf(self):
        """GPU Real-Time Factor should be well under 1.0."""
        _, avg_time, audio_dur, _ = _time_piper_synthesis(use_cuda=True)
        rtf = avg_time / audio_dur if audio_dur > 0 else float("inf")
        print(f"\n  GPU: synth={avg_time:.3f}s  audio={audio_dur:.2f}s  RTF={rtf:.3f}")

        assert rtf < 0.5, (
            f"GPU RTF={rtf:.3f}; expected < 0.5 for smooth voice response"
        )

    def test_piper_fits_in_gtx960(self, gtx960):
        """Piper TTS should use minimal VRAM on GTX 960."""
        _, _, _, peak_vram = _time_piper_synthesis(use_cuda=True)
        max_allowed = 500  # Piper models are small; should use well under 500 MiB
        print(f"\n  Peak VRAM: {peak_vram:.0f} MiB / {gtx960['memory_total_mib']} MiB")

        assert peak_vram < max_allowed, (
            f"Piper uses {peak_vram:.0f} MiB; expected < {max_allowed} MiB"
        )


class TestPiperGPUReadiness:
    """
    Summary test that reports what needs to change for GPU enablement.
    Always runs -- acts as a checklist.
    """

    def test_gpu_readiness_report(self):
        issues = []

        # Check onnxruntime-gpu
        try:
            import onnxruntime
            if "CUDAExecutionProvider" not in onnxruntime.get_available_providers():
                issues.append(
                    "BLOCKED: onnxruntime-gpu not installed "
                    "(replace onnxruntime with onnxruntime-gpu in mouth/pyproject.toml)"
                )
        except ImportError:
            issues.append("BLOCKED: onnxruntime not installed at all")

        # Check Piper model
        if _find_piper_model() is None:
            issues.append("BLOCKED: No Piper ONNX model found")

        # Check CUDA availability
        try:
            import torch
            if not torch.cuda.is_available():
                issues.append(
                    "BLOCKED: torch.cuda not available "
                    "(MOUTH Dockerfile uses python:3.11-slim; needs CUDA base)"
                )
        except ImportError:
            issues.append(
                "BLOCKED: PyTorch not installed "
                "(needed by onnxruntime-gpu for CUDA memory management)"
            )

        # Check synthesizer code
        import inspect
        try:
            from piper import PiperVoice
            sig = inspect.signature(PiperVoice.load)
            if "use_cuda" in sig.parameters:
                # Good - Piper supports it. But is MOUTH using it?
                pass
        except Exception:
            issues.append("BLOCKED: piper not installed")

        if issues:
            msg = "MOUTH GPU readiness issues:\n" + "\n".join(f"  - {i}" for i in issues)
            print(f"\n{msg}")
            pytest.skip(msg)
        else:
            print("\n  All GPU readiness checks passed")
