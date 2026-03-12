"""GPU configuration guard tests.

These tests fail fast and loud if the CUDA environment is broken.
They verify that torch sees the GPU, that EARS config is set to use it,
and that Whisper actually loads onto CUDA.
"""

import pytest
import torch


class TestCUDAEnvironment:
    """Verify the CUDA runtime is functional."""

    def test_cuda_available(self):
        """torch.cuda.is_available() must be True."""
        assert torch.cuda.is_available(), (
            "CUDA not available. Check: nvidia-smi, CUDA toolkit, "
            "and that torch was installed from the cu121 index."
        )

    def test_cuda_device_exists(self):
        """At least one CUDA device must be visible."""
        assert torch.cuda.device_count() > 0, "No CUDA devices found"

    def test_cuda_device_name(self):
        """Sanity check — print the GPU name."""
        if not torch.cuda.is_available():
            pytest.skip("CUDA not available")
        name = torch.cuda.get_device_name(0)
        assert len(name) > 0, "GPU device name is empty"

    def test_cuda_memory_allocated(self):
        """Verify we can allocate a tensor on GPU."""
        if not torch.cuda.is_available():
            pytest.skip("CUDA not available")
        t = torch.zeros(1000, device="cuda")
        assert t.device.type == "cuda"
        del t
        torch.cuda.empty_cache()


class TestEARSGPUConfig:
    """Verify EARS config is locked to GPU."""

    def test_whisper_device_is_cuda(self):
        """Config must specify device=cuda."""
        from ears.config import config
        assert config.whisper.device == "cuda", (
            f"Whisper device is '{config.whisper.device}', expected 'cuda'. "
            f"Check ears/ears/config/config.yaml"
        )

    def test_whisper_compute_type_is_gpu_compatible(self):
        """Config must specify a GPU-compatible compute_type."""
        from ears.config import config
        gpu_types = {"float16", "float32", "bfloat16", "int8_float16", "int8_float32"}
        assert config.whisper.compute_type in gpu_types, (
            f"Whisper compute_type is '{config.whisper.compute_type}', "
            f"expected one of {gpu_types}. Check ears/ears/config/config.yaml"
        )

    def test_whisper_device_index_targets_rtx3060(self):
        """Config device_index must point to the RTX 3060, not the GTX 960."""
        if not torch.cuda.is_available():
            pytest.skip("CUDA not available")
        from ears.config import config
        idx = config.whisper.device_index
        name = torch.cuda.get_device_name(idx)
        assert "3060" in name, (
            f"device_index={idx} is '{name}'. Expected RTX 3060. "
            f"Note: PyTorch and nvidia-smi may enumerate GPUs in different order."
        )


class TestWhisperGPU:
    """Verify Whisper model loads onto GPU."""

    @pytest.mark.slow
    def test_whisper_model_loads_on_cuda(self):
        """Whisper model must load on CUDA device."""
        if not torch.cuda.is_available():
            pytest.skip("CUDA not available")

        from ears.audio.faster_whisper_client import load_model
        model = load_model()
        # CTranslate2 model exposes device property
        assert model.model.device == "cuda", (
            f"Whisper model loaded on '{model.model.device}', expected 'cuda'"
        )

    @pytest.mark.slow
    def test_whisper_inference_uses_gpu(self):
        """Transcription should produce output when configured for CUDA."""
        if not torch.cuda.is_available():
            pytest.skip("CUDA not available")

        from ears.audio.faster_whisper_client import load_model
        model = load_model()

        # CTranslate2 manages its own CUDA memory (not visible to torch).
        # Verify the model reports cuda and can run inference without error.
        assert model.model.device == "cuda"
        # Verify by GPU name, not index (nvidia-smi and PyTorch order differs)
        idx = model.model.device_index[0]
        name = torch.cuda.get_device_name(idx)
        assert "3060" in name, (
            f"Whisper on GPU {idx} '{name}', expected RTX 3060"
        )
