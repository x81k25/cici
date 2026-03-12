"""
GPU Availability Tests

Verify that the host has the expected GPUs, drivers, and CUDA runtime
before testing individual services. These are the foundation tests --
if these fail, service-level GPU tests are meaningless.
"""

import subprocess
import pytest


class TestDriverAndRuntime:
    """Verify NVIDIA driver and CUDA runtime are functional."""

    def test_nvidia_smi_available(self):
        result = subprocess.run(
            ["nvidia-smi"], capture_output=True, text=True
        )
        assert result.returncode == 0, "nvidia-smi not found or failed"

    def test_cuda_driver_version(self):
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
            capture_output=True, text=True,
        )
        version = result.stdout.strip()
        major = int(version.split(".")[0])
        assert major >= 525, f"Driver {version} too old; need >= 525 for CUDA 12.x"

    def test_two_gpus_visible(self, gpu_inventory):
        assert len(gpu_inventory) == 2, (
            f"Expected 2 GPUs, found {len(gpu_inventory)}: "
            f"{[g['name'] for g in gpu_inventory]}"
        )


class TestGTX960:
    """Verify GTX 960 is present and has expected capabilities."""

    def test_exists(self, gtx960):
        assert "960" in gtx960["name"]

    def test_vram(self, gtx960):
        assert gtx960["memory_total_mib"] >= 3800, (
            f"GTX 960 reports {gtx960['memory_total_mib']} MiB; expected ~4096"
        )

    def test_compute_capability(self, gtx960):
        major, minor = gtx960["compute_cap"].split(".")
        cap = float(gtx960["compute_cap"])
        assert cap >= 5.0, (
            f"Compute capability {cap} too low for CUDA inference (need >= 5.0)"
        )


class TestRTX3060:
    """Verify RTX 3060 is present and has expected capabilities."""

    def test_exists(self, rtx3060):
        assert "3060" in rtx3060["name"]

    def test_vram(self, rtx3060):
        assert rtx3060["memory_total_mib"] >= 12000, (
            f"RTX 3060 reports {rtx3060['memory_total_mib']} MiB; expected ~12288"
        )

    def test_compute_capability(self, rtx3060):
        cap = float(rtx3060["compute_cap"])
        assert cap >= 8.0, (
            f"Compute capability {cap}; expected >= 8.0 for Ampere"
        )


class TestPyTorchCUDA:
    """Verify PyTorch can see and use CUDA."""

    def test_torch_cuda_available(self):
        import torch
        assert torch.cuda.is_available(), (
            "torch.cuda.is_available() is False -- "
            "PyTorch was built without CUDA or driver mismatch"
        )

    def test_torch_device_count(self):
        import torch
        count = torch.cuda.device_count()
        assert count >= 1, f"torch sees {count} CUDA devices; expected >= 1"

    def test_torch_can_allocate_on_compatible_devices(self):
        """Smoke test: allocate a small tensor on each compatible GPU."""
        import torch
        allocated = []
        for i in range(torch.cuda.device_count()):
            cap = torch.cuda.get_device_capability(i)
            name = torch.cuda.get_device_name(i)
            # PyTorch 2.x requires compute capability >= 7.0 (Volta+)
            if cap[0] < 7:
                print(f"\n  Skipping cuda:{i} ({name}) — "
                      f"compute cap {cap[0]}.{cap[1]} < 7.0 (unsupported by PyTorch)")
                continue
            t = torch.zeros(64, device=f"cuda:{i}")
            assert t.device.type == "cuda"
            allocated.append(name)
            del t
            torch.cuda.empty_cache()
        assert len(allocated) > 0, "No compatible CUDA devices found"

    def test_torch_cuda_version(self):
        import torch
        version = torch.version.cuda
        assert version is not None, "torch.version.cuda is None"
        major = int(version.split(".")[0])
        assert major >= 12, f"PyTorch CUDA {version}; need >= 12.x"


class TestONNXRuntimeCUDA:
    """Verify ONNX Runtime can use CUDA (needed for MOUTH/Piper)."""

    def test_onnxruntime_installed(self):
        import onnxruntime
        assert onnxruntime.__version__

    def test_cuda_execution_provider_available(self):
        import onnxruntime
        providers = onnxruntime.get_available_providers()
        assert "CUDAExecutionProvider" in providers, (
            f"CUDAExecutionProvider not in {providers}. "
            "Install onnxruntime-gpu instead of onnxruntime."
        )
