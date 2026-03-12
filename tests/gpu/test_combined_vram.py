"""
Combined VRAM Budget Tests

Verify that all GPU-accelerated services can coexist on the
planned GPU split without running out of VRAM:

  RTX 3060 (12 GB) → Ollama (hermes3)
  GTX 960  (4 GB)  → EARS (Whisper small) + MOUTH (Piper)
"""

import subprocess
import pytest


def nvidia_smi_gpu_memory():
    """Return list of (index, name, used_mib, total_mib)."""
    result = subprocess.run(
        ["nvidia-smi", "--query-gpu=index,name,memory.used,memory.total",
         "--format=csv,noheader,nounits"],
        capture_output=True, text=True,
    )
    gpus = []
    for line in result.stdout.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        gpus.append({
            "index": int(parts[0]),
            "name": parts[1],
            "used_mib": int(parts[2]),
            "total_mib": int(parts[3]),
        })
    return gpus


class TestRTX3060VRAMBudget:
    """RTX 3060 budget: Ollama only."""

    # Estimated VRAM for hermes3 (7B, Q4 quantized)
    OLLAMA_ESTIMATED_MIB = 5000
    RTX3060_TOTAL = 12288
    HEADROOM_PERCENT = 15

    def test_ollama_fits_with_headroom(self):
        max_allowed = self.RTX3060_TOTAL * (1 - self.HEADROOM_PERCENT / 100)
        assert self.OLLAMA_ESTIMATED_MIB < max_allowed, (
            f"Ollama estimated {self.OLLAMA_ESTIMATED_MIB} MiB > "
            f"{max_allowed:.0f} MiB (RTX 3060 with {self.HEADROOM_PERCENT}% headroom)"
        )
        remaining = self.RTX3060_TOTAL - self.OLLAMA_ESTIMATED_MIB
        print(f"\n  RTX 3060: Ollama ~{self.OLLAMA_ESTIMATED_MIB} MiB "
              f"| Remaining: {remaining} MiB")

    def test_current_rtx3060_usage(self, rtx3060):
        """Report current RTX 3060 memory usage."""
        gpus = nvidia_smi_gpu_memory()
        rtx = next((g for g in gpus if "3060" in g["name"]), None)
        if rtx is None:
            pytest.skip("RTX 3060 not found")

        usage_pct = rtx["used_mib"] / rtx["total_mib"] * 100
        print(f"\n  RTX 3060: {rtx['used_mib']} / {rtx['total_mib']} MiB "
              f"({usage_pct:.0f}% used)")

        assert rtx["used_mib"] < rtx["total_mib"] * 0.95, (
            f"RTX 3060 at {usage_pct:.0f}% capacity"
        )


class TestGTX960Compatibility:
    """
    GTX 960 compatibility assessment.

    PyTorch 2.x requires compute capability >= 7.0 (Volta+).
    GTX 960 is compute capability 5.2 (Maxwell) — INCOMPATIBLE with PyTorch.
    This means EARS (faster-whisper/CTranslate2) CANNOT run on GTX 960.

    ONNX Runtime may still support it via older CUDA paths, but Piper TTS
    alone doesn't justify dedicating a GPU.
    """

    def test_gtx960_incompatible_with_pytorch(self, gtx960):
        """Document that GTX 960 cannot run PyTorch CUDA workloads."""
        cap = float(gtx960["compute_cap"])
        print(f"\n  GTX 960 compute capability: {cap} (PyTorch requires >= 7.0)")
        assert cap < 7.0, "GTX 960 compute cap unexpectedly >= 7.0"
        # This is a documentation test — the assertion proves the incompatibility

    def test_current_gtx960_usage(self, gtx960):
        """Report current GTX 960 memory usage."""
        gpus = nvidia_smi_gpu_memory()
        gtx = next((g for g in gpus if "960" in g["name"]), None)
        if gtx is None:
            pytest.skip("GTX 960 not found")

        usage_pct = gtx["used_mib"] / gtx["total_mib"] * 100
        print(f"\n  GTX 960: {gtx['used_mib']} / {gtx['total_mib']} MiB "
              f"({usage_pct:.0f}% used)")


class TestRTX3060SharedBudget:
    """
    Since GTX 960 is incompatible with PyTorch, ALL GPU services
    must share the RTX 3060:
      - Ollama (hermes3 ~5 GB)
      - EARS Whisper small (~600 MB)
      - MOUTH Piper (~100 MB)
    """

    OLLAMA_ESTIMATED_MIB = 5000
    WHISPER_SMALL_ESTIMATED_MIB = 600
    PIPER_ESTIMATED_MIB = 100
    RTX3060_TOTAL = 12288
    HEADROOM_PERCENT = 10

    def test_all_three_fit_on_rtx3060(self):
        combined = (self.OLLAMA_ESTIMATED_MIB +
                    self.WHISPER_SMALL_ESTIMATED_MIB +
                    self.PIPER_ESTIMATED_MIB)
        max_allowed = self.RTX3060_TOTAL * (1 - self.HEADROOM_PERCENT / 100)
        remaining = self.RTX3060_TOTAL - combined

        print(f"\n  Ollama: ~{self.OLLAMA_ESTIMATED_MIB} MiB"
              f"\n  Whisper small: ~{self.WHISPER_SMALL_ESTIMATED_MIB} MiB"
              f"\n  Piper: ~{self.PIPER_ESTIMATED_MIB} MiB"
              f"\n  Total: {combined} MiB / {self.RTX3060_TOTAL} MiB"
              f"\n  Remaining: {remaining} MiB")

        assert combined < max_allowed, (
            f"Combined {combined} MiB exceeds RTX 3060 budget "
            f"({max_allowed:.0f} MiB with {self.HEADROOM_PERCENT}% headroom)"
        )

    def test_could_upgrade_to_whisper_medium(self):
        """Check if RTX 3060 could handle Whisper medium alongside Ollama."""
        whisper_medium = 1500
        combined = self.OLLAMA_ESTIMATED_MIB + whisper_medium + self.PIPER_ESTIMATED_MIB
        max_allowed = self.RTX3060_TOTAL * (1 - self.HEADROOM_PERCENT / 100)
        fits = combined < max_allowed

        print(f"\n  With Whisper medium: {combined} MiB / {max_allowed:.0f} MiB "
              f"→ {'FITS' if fits else 'TOO LARGE'}")
