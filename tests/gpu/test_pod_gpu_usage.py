"""
Pod-Level GPU Usage Tests

Verify that all GPU-dependent k8s pods are actually consuming VRAM on
the expected GPU (RTX 3060). These tests query nvidia-smi for active
GPU processes and correlate them with running pods.

Active GPU pods:
  - local-llm (Ollama) — must be on RTX 3060
  - cici-ears — must be on RTX 3060 (when GPU-enabled)
  - cici-mouth — future (currently CPU)
"""

import subprocess
import pytest
import httpx


BACKEND_HOST = "192.168.50.2"
OLLAMA_PORT = 31435
MIND_PORT = 30211
EARS_PORT = 30212
MOUTH_PORT = 30213


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_gpu_processes():
    """Return list of GPU compute processes from nvidia-smi."""
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


def _get_running_pods(namespace="ai-ml"):
    """Return list of running pod names in the namespace."""
    result = subprocess.run(
        ["kubectl", "get", "pods", "-n", namespace,
         "--field-selector=status.phase=Running",
         "-o", "jsonpath={.items[*].metadata.name}"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return []
    return result.stdout.strip().split()


def _pod_is_running(prefix, namespace="ai-ml"):
    """Check if any pod with the given name prefix is Running."""
    pods = _get_running_pods(namespace)
    return any(p.startswith(prefix) for p in pods)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestOllamaGPUPod:
    """Verify the local-llm (Ollama) pod is using the RTX 3060."""

    def test_pod_is_running(self):
        assert _pod_is_running("local-llm"), "local-llm pod not running"

    def test_ollama_responds(self):
        resp = httpx.get(f"http://{BACKEND_HOST}:{OLLAMA_PORT}/", timeout=5)
        assert resp.status_code == 200

    def test_ollama_on_rtx3060(self, rtx3060):
        """After triggering inference, Ollama should be on RTX 3060."""
        # Trigger model load
        httpx.post(
            f"http://{BACKEND_HOST}:{OLLAMA_PORT}/api/generate",
            json={"model": "hermes3", "prompt": "hi", "stream": False,
                  "options": {"num_predict": 3}},
            timeout=60,
        )

        procs = _get_gpu_processes()
        rtx_uuid = rtx3060["uuid"]
        on_rtx = [p for p in procs if p["gpu_uuid"] == rtx_uuid]

        assert on_rtx, (
            f"No GPU processes on RTX 3060 after Ollama inference. "
            f"All processes: {procs}"
        )
        total_mib = sum(p["used_mib"] for p in on_rtx)
        print(f"\n  Ollama GPU usage on RTX 3060: {total_mib} MiB")
        # hermes3 7B should use at least 2GB
        assert total_mib > 2000, (
            f"Only {total_mib} MiB on RTX 3060; model may not be fully loaded"
        )


class TestEarsGPUPod:
    """Verify the cici-ears pod GPU configuration.

    NOTE: EARS GPU in k8s requires:
      1. GPU-enabled Docker image (torch-base with CUDA)
      2. NVIDIA device plugin scheduling GPU to the pod
      3. config.yaml with device: cuda

    If the pod is running without GPU access, these tests document
    that and report the expected state.
    """

    def test_pod_is_running(self):
        assert _pod_is_running("cici-ears"), "cici-ears pod not running"

    def test_ears_websocket_accessible(self):
        """EARS should accept WebSocket connections on its NodePort."""
        # Just check TCP connectivity, not a full WebSocket handshake
        result = subprocess.run(
            ["nc", "-z", "-w", "3", BACKEND_HOST, str(EARS_PORT)],
            capture_output=True,
        )
        assert result.returncode == 0, (
            f"Cannot reach EARS at {BACKEND_HOST}:{EARS_PORT}"
        )

    def test_ears_pod_has_gpu_resources(self):
        """Check if the EARS pod has GPU resources allocated by k8s."""
        result = subprocess.run(
            ["kubectl", "get", "pod", "-n", "ai-ml",
             "-l", "app=cici-ears",
             "-o", "jsonpath={.items[0].spec.containers[0].resources}"],
            capture_output=True, text=True,
        )
        has_gpu = "nvidia.com/gpu" in result.stdout
        if not has_gpu:
            pytest.skip(
                "EARS pod does not have nvidia.com/gpu resources. "
                "Add GPU resource requests to the deployment manifest "
                "and ensure NVIDIA device plugin is running."
            )
        print(f"\n  EARS pod resources: {result.stdout}")

    def test_ears_config_is_cuda(self):
        """EARS config inside the pod should specify device=cuda."""
        result = subprocess.run(
            ["kubectl", "exec", "-n", "ai-ml", "deploy/cici-ears", "--",
             "python", "-c",
             "from ears.config import config; print(config.whisper.device)"],
            capture_output=True, text=True, timeout=15,
        )
        device = result.stdout.strip()
        if device != "cuda":
            pytest.skip(
                f"EARS pod config has device='{device}', not 'cuda'. "
                "Rebuild and redeploy with updated config.yaml."
            )
        print(f"\n  EARS pod whisper device: {device}")


class TestMouthGPUPod:
    """Verify MOUTH pod state (currently CPU, GPU planned)."""

    def test_pod_is_running(self):
        assert _pod_is_running("cici-mouth"), "cici-mouth pod not running"

    def test_mouth_health(self):
        resp = httpx.get(
            f"http://{BACKEND_HOST}:{MOUTH_PORT}/health", timeout=5
        )
        assert resp.status_code == 200

    def test_mouth_gpu_readiness(self):
        """Report whether MOUTH pod has GPU support.

        MOUTH GPU requires onnxruntime-gpu and a CUDA-enabled Docker image.
        Currently MOUTH runs on CPU — this test documents the gap.
        """
        result = subprocess.run(
            ["kubectl", "get", "pod", "-n", "ai-ml",
             "-l", "app=cici-mouth",
             "-o", "jsonpath={.items[0].spec.containers[0].resources}"],
            capture_output=True, text=True,
        )
        has_gpu = "nvidia.com/gpu" in result.stdout
        if not has_gpu:
            pytest.skip(
                "MOUTH pod runs on CPU (expected for now). "
                "GPU enablement requires: onnxruntime-gpu, CUDA base image, "
                "and nvidia.com/gpu resource request."
            )


class TestAllPodsGPUSummary:
    """Summary: verify all GPU-dependent pods are on the correct GPU."""

    def test_no_gpu_processes_on_gtx960(self, gtx960):
        """No CICI services should be on the GTX 960 (incompatible)."""
        procs = _get_gpu_processes()
        gtx_uuid = gtx960["uuid"]
        on_gtx = [p for p in procs if p["gpu_uuid"] == gtx_uuid]

        if on_gtx:
            names = [p["name"] for p in on_gtx]
            # Xorg/display server is fine, just not our services
            service_procs = [
                p for p in on_gtx
                if not any(x in p["name"].lower() for x in ["xorg", "x11", "gnome", "display"])
            ]
            if service_procs:
                pytest.fail(
                    f"GPU processes on GTX 960 (should be on RTX 3060): "
                    f"{service_procs}"
                )

    def test_rtx3060_has_headroom(self, rtx3060):
        """RTX 3060 should have at least 10% VRAM free."""
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True,
        )
        for line in result.stdout.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            used, total = int(parts[0]), int(parts[1])
            # Find the RTX 3060 row (largest VRAM)
            if total > 10000:
                usage_pct = used / total * 100
                remaining = total - used
                print(f"\n  RTX 3060: {used}/{total} MiB ({usage_pct:.0f}% used, "
                      f"{remaining} MiB free)")
                assert usage_pct < 90, (
                    f"RTX 3060 at {usage_pct:.0f}% — less than 10% headroom"
                )
                return
        pytest.skip("Could not find RTX 3060 in nvidia-smi output")
