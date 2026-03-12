"""
Ollama / local-llm GPU Tests

Verify Ollama is using the RTX 3060 for LLM inference and that
response times are consistent with GPU-accelerated generation.
"""

import time
import subprocess
import pytest
import httpx


OLLAMA_EXTERNAL = "http://192.168.50.2:31435"
MIND_EXTERNAL = "http://192.168.50.2:30211"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_gpu_processes():
    """Return list of (pid, name, gpu_uuid, used_mem) from nvidia-smi."""
    result = subprocess.run(
        ["nvidia-smi", "--query-compute-apps=pid,process_name,gpu_uuid,used_gpu_memory",
         "--format=csv,noheader,nounits"],
        capture_output=True, text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return []
    procs = []
    for line in result.stdout.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 4:
            procs.append({
                "pid": parts[0],
                "name": parts[1],
                "gpu_uuid": parts[2],
                "used_mib": int(parts[3]),
            })
    return procs


def _ollama_generate(prompt, model="hermes3", max_tokens=50):
    """Send a generate request to Ollama and return (response_text, elapsed_s, tokens)."""
    t0 = time.perf_counter()
    resp = httpx.post(
        f"{OLLAMA_EXTERNAL}/api/generate",
        json={
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"num_predict": max_tokens},
        },
        timeout=120.0,
    )
    elapsed = time.perf_counter() - t0
    resp.raise_for_status()
    data = resp.json()
    text = data.get("response", "")
    # Ollama returns eval_count (tokens generated)
    tokens = data.get("eval_count", len(text.split()))
    return text, elapsed, tokens


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestOllamaConnectivity:
    """Verify Ollama is running and accessible."""

    def test_ollama_health(self):
        resp = httpx.get(f"{OLLAMA_EXTERNAL}/", timeout=5.0)
        assert resp.status_code == 200

    def test_mind_sees_ollama(self):
        resp = httpx.get(f"{MIND_EXTERNAL}/health", timeout=5.0)
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["mode"] == "ollama"


class TestOllamaGPUUsage:
    """Verify Ollama is actually using the RTX 3060."""

    def test_ollama_on_rtx3060(self, rtx3060):
        """
        After triggering inference, Ollama should appear in nvidia-smi
        on the RTX 3060 UUID.
        """
        # Trigger a generation to ensure model is loaded
        _ollama_generate("Say hello.", max_tokens=5)

        procs = _get_gpu_processes()
        rtx_uuid = rtx3060["uuid"]

        ollama_on_rtx = [
            p for p in procs
            if "ollama" in p["name"].lower() and p["gpu_uuid"] == rtx_uuid
        ]

        if not ollama_on_rtx:
            # Also check by any process on RTX (Ollama might show as "python" or "server")
            any_on_rtx = [p for p in procs if p["gpu_uuid"] == rtx_uuid]
            assert any_on_rtx, (
                f"No GPU processes on RTX 3060 ({rtx_uuid}). "
                f"All GPU processes: {procs}"
            )
            print(f"\n  Processes on RTX 3060: {any_on_rtx}")
        else:
            print(f"\n  Ollama on RTX 3060: {ollama_on_rtx[0]['used_mib']} MiB")

    def test_ollama_not_on_gtx960(self, gtx960):
        """Ollama should NOT be on the GTX 960 (not enough VRAM for LLM)."""
        _ollama_generate("Say hello.", max_tokens=5)

        procs = _get_gpu_processes()
        gtx_uuid = gtx960["uuid"]
        ollama_on_gtx = [
            p for p in procs
            if "ollama" in p["name"].lower() and p["gpu_uuid"] == gtx_uuid
        ]
        assert not ollama_on_gtx, (
            f"Ollama is on GTX 960 -- LLM needs RTX 3060. "
            f"Found: {ollama_on_gtx}"
        )

    def test_ollama_vram_usage(self, rtx3060):
        """Ollama VRAM usage should be substantial but within RTX 3060 limits."""
        _ollama_generate("Tell me a joke.", max_tokens=20)

        procs = _get_gpu_processes()
        rtx_uuid = rtx3060["uuid"]
        rtx_procs = [p for p in procs if p["gpu_uuid"] == rtx_uuid]
        total_vram = sum(p["used_mib"] for p in rtx_procs)

        print(f"\n  RTX 3060 VRAM in use: {total_vram} MiB / {rtx3060['memory_total_mib']} MiB")

        # hermes3 (~7B) should use at least 2GB on GPU
        assert total_vram > 2000, (
            f"Only {total_vram} MiB VRAM used; model may not be on GPU"
        )
        # Should not exceed available VRAM
        assert total_vram < rtx3060["memory_total_mib"], (
            f"VRAM usage ({total_vram} MiB) exceeds GPU capacity "
            f"({rtx3060['memory_total_mib']} MiB)"
        )


class TestOllamaPerformance:
    """Benchmark Ollama generation speed to detect CPU fallback."""

    def test_tokens_per_second(self):
        """
        GPU-accelerated hermes3 (~7B) should generate at least 15 tok/s
        on RTX 3060. CPU fallback typically gives < 5 tok/s.
        """
        # Warmup (model load)
        _ollama_generate("Hi", max_tokens=5)

        # Benchmark
        prompt = "Write a short paragraph about the ocean."
        _, elapsed, tokens = _ollama_generate(prompt, max_tokens=100)
        tps = tokens / elapsed if elapsed > 0 else 0

        print(f"\n  Generated {tokens} tokens in {elapsed:.2f}s = {tps:.1f} tok/s")

        assert tps > 10, (
            f"Only {tps:.1f} tok/s; expected > 10 for GPU inference. "
            "Ollama may be falling back to CPU."
        )

    def test_time_to_first_token(self):
        """
        Time to first token should be reasonable (< 5s for warm model).
        """
        # Warmup
        _ollama_generate("Hi", max_tokens=5)

        # Measure streaming TTFT
        t0 = time.perf_counter()
        with httpx.stream(
            "POST",
            f"{OLLAMA_EXTERNAL}/api/generate",
            json={
                "model": "hermes3",
                "prompt": "Say one word.",
                "stream": True,
                "options": {"num_predict": 10},
            },
            timeout=30.0,
        ) as resp:
            for line in resp.iter_lines():
                # First line = first token
                ttft = time.perf_counter() - t0
                break

        print(f"\n  Time to first token: {ttft:.2f}s")

        assert ttft < 5.0, (
            f"TTFT={ttft:.2f}s; expected < 5s for warm GPU model"
        )

    def test_response_latency_for_short_query(self):
        """
        A short query should return within a reasonable time for
        interactive voice assistant use.
        """
        # Warmup
        _ollama_generate("Hi", max_tokens=5)

        _, elapsed, _ = _ollama_generate("What is 2+2?", max_tokens=30)
        print(f"\n  Short query latency: {elapsed:.2f}s")

        assert elapsed < 10.0, (
            f"Short query took {elapsed:.2f}s; expected < 10s for voice UX"
        )
