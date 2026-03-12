"""
E2E test fixtures. Helpers are in helpers.py.
"""

import sys
import time
from pathlib import Path

import httpx
import pytest

# Add e2e directory to path so helpers can be imported
sys.path.insert(0, str(Path(__file__).parent))

from helpers import (  # noqa: E402
    BACKEND_HOST,
    MIND_PORT,
    MOUTH_PORT,
    AdbHelper,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def adb():
    """Verified ADB connection with mic permission granted."""
    helper = AdbHelper()
    assert helper.is_device_connected(), "No ADB device connected"
    helper.grant_mic_permission()
    return helper


@pytest.fixture(scope="session")
def backend_health():
    """Verify MIND and MOUTH backends are reachable."""
    mind_ok = False
    mouth_ok = False
    try:
        r = httpx.get(f"http://{BACKEND_HOST}:{MIND_PORT}/health", timeout=5)
        mind_ok = r.status_code == 200
    except Exception:
        pass
    try:
        r = httpx.get(f"http://{BACKEND_HOST}:{MOUTH_PORT}/health", timeout=5)
        mouth_ok = r.status_code == 200
    except Exception:
        pass
    return {"mind": mind_ok, "mouth": mouth_ok}


@pytest.fixture(autouse=True)
def app_ready(adb: AdbHelper):
    """Ensure app is launched and in foreground before each test."""
    if not adb.is_app_foreground():
        adb.launch_app()
        time.sleep(1)
    yield


@pytest.fixture
def fresh_app(adb: AdbHelper):
    """Force restart app for a clean state."""
    adb.force_stop_app()
    adb.launch_app()
    time.sleep(2)
    yield


@pytest.fixture
def reset_mode(adb: AdbHelper):
    """Reset to ollama mode via direct API call, clearing message buffer."""
    try:
        httpx.post(
            f"http://{BACKEND_HOST}:{MIND_PORT}/text",
            json={"text": "ollama mode"},
            timeout=10,
        )
        httpx.get(f"http://{BACKEND_HOST}:{MIND_PORT}/messages", timeout=5)
        time.sleep(0.5)
    except Exception:
        pass
    yield


@pytest.fixture(scope="session")
def mind_api():
    """httpx client for direct MIND backend calls."""
    client = httpx.Client(
        base_url=f"http://{BACKEND_HOST}:{MIND_PORT}",
        timeout=30,
    )
    yield client
    client.close()


@pytest.fixture(scope="session")
def mouth_api():
    """httpx client for direct MOUTH backend calls."""
    client = httpx.Client(
        base_url=f"http://{BACKEND_HOST}:{MOUTH_PORT}",
        timeout=10,
    )
    yield client
    client.close()


# ---------------------------------------------------------------------------
# Markers
# ---------------------------------------------------------------------------

def pytest_configure(config):
    config.addinivalue_line("markers", "smoke: basic connectivity and health tests")
    config.addinivalue_line("markers", "text: text input/output tests")
    config.addinivalue_line("markers", "voice: microphone and transcription tests")
    config.addinivalue_line("markers", "mode_switch: mode transition tests")
    config.addinivalue_line("markers", "edge_case: edge case and error handling tests")
    config.addinivalue_line("markers", "tts: text-to-speech tests")
    config.addinivalue_line("markers", "slow: long-running tests")
