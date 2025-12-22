# standard library imports
import json
import multiprocessing
import sys
import time
from pathlib import Path

# 3rd-party imports
import pytest


# ------------------------------------------------------------------------------
# path setup for cross-module imports
# ------------------------------------------------------------------------------

# Add module directories to path for imports
CICI_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(CICI_ROOT / "ears"))
sys.path.insert(0, str(CICI_ROOT / "mind"))
sys.path.insert(0, str(CICI_ROOT / "face"))


# ------------------------------------------------------------------------------
# pytest configuration
# ------------------------------------------------------------------------------

def pytest_configure(config):
    """Configure pytest markers."""
    config.addinivalue_line(
        "markers", "asyncio: mark test as async"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow (requires model loading or network)"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as integration tests"
    )


# ------------------------------------------------------------------------------
# audio fixtures
# ------------------------------------------------------------------------------

AUDIO_DIR = Path(__file__).parent / "audio"


@pytest.fixture
def audio_dir() -> Path:
    """Return the path to the test audio directory."""
    return AUDIO_DIR


@pytest.fixture
def test_audio_files() -> list[Path]:
    """Return list of available test audio files."""
    if not AUDIO_DIR.exists():
        return []
    return list(AUDIO_DIR.glob("*.webm")) + list(AUDIO_DIR.glob("*.wav"))


# ------------------------------------------------------------------------------
# MIND server fixtures
# ------------------------------------------------------------------------------

MIND_TEST_HOST = "localhost"
MIND_TEST_PORT = 18765  # non-standard port for integration testing


def run_mind_server_process(host: str, port: int, ready_event: multiprocessing.Event):
    """Run the MIND server in a subprocess."""
    import uvicorn
    sys.path.insert(0, str(CICI_ROOT / "mind"))
    from mind.main import app

    # Signal ready before starting (uvicorn blocks)
    def on_startup():
        ready_event.set()

    # Add startup callback
    original_lifespan = app.router.lifespan_context

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def lifespan_with_signal(app):
        async with original_lifespan(app):
            ready_event.set()
            yield

    app.router.lifespan_context = lifespan_with_signal

    uvicorn.run(app, host=host, port=port, log_level="warning")


@pytest.fixture(scope="module")
def mind_server():
    """Start MIND server for the test module, shut down after."""
    ready_event = multiprocessing.Event()
    server_process = multiprocessing.Process(
        target=run_mind_server_process,
        args=(MIND_TEST_HOST, MIND_TEST_PORT, ready_event),
        daemon=True,
    )
    server_process.start()

    # Wait for server to be ready
    ready_event.wait(timeout=30)
    time.sleep(1)  # Give server time to fully initialize

    yield f"http://{MIND_TEST_HOST}:{MIND_TEST_PORT}"

    # Shutdown
    server_process.terminate()
    server_process.join(timeout=5)
    if server_process.is_alive():
        server_process.kill()


@pytest.fixture
def mind_api_url(mind_server) -> str:
    """Return the MIND API URL."""
    return mind_server


# ------------------------------------------------------------------------------
# defect audio fixtures
# ------------------------------------------------------------------------------

DEFECT_AUDIO_DIR = Path(__file__).parent / "audio" / "defective"


@pytest.fixture
def defect_audio_dir() -> Path:
    """Return the path to the defective audio directory."""
    return DEFECT_AUDIO_DIR


@pytest.fixture
def defect_audio_files() -> list[Path]:
    """Return list of available defective audio files."""
    if not DEFECT_AUDIO_DIR.exists():
        return []
    return list(DEFECT_AUDIO_DIR.glob("*.webm")) + list(DEFECT_AUDIO_DIR.glob("*.raw"))


@pytest.fixture
def defect_test_cases() -> list[dict]:
    """Return the defect test cases from defects.json."""
    defects_file = DEFECT_AUDIO_DIR / "defects.json"
    if not defects_file.exists():
        return []
    with open(defects_file, "r") as f:
        return json.load(f)
