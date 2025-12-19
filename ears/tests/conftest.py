# standard library imports
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

# 3rd-party imports
import pytest
import pytest_asyncio


# ------------------------------------------------------------------------------
# pytest configuration
# ------------------------------------------------------------------------------

def pytest_configure(config):
    """Configure pytest-asyncio mode."""
    config.addinivalue_line(
        "markers", "asyncio: mark test as async"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow (requires model loading)"
    )


# ------------------------------------------------------------------------------
# fixtures
# ------------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "audio"


@pytest.fixture
def mock_websocket():
    """Create a mock WebSocket connection."""
    ws = AsyncMock()
    ws.remote_address = ("127.0.0.1", 12345)
    ws.send = AsyncMock()
    ws.close = AsyncMock()
    return ws


@pytest.fixture
def sample_speech_audio() -> bytes:
    """Load the sample speech audio file."""
    # Try the ears fixtures first, then fall back to parent project
    audio_path = FIXTURES_DIR / "sample_speech.wav"
    if not audio_path.exists():
        # fall back to parent project fixtures
        parent_fixtures = Path(__file__).parent.parent.parent / "tests" / "fixtures" / "audio"
        audio_path = parent_fixtures / "sample_speech.wav"

    if not audio_path.exists():
        pytest.skip(f"Test audio file not found: {audio_path}")

    with open(audio_path, "rb") as f:
        return f.read()


@pytest.fixture
def expected_phrases() -> list[str]:
    """Known phrases from the Open Speech Repository sample."""
    return [
        "birch canoe",
        "smooth plank",
        "dark blue background",
        "depth of a well",
        "chicken leg",
        "round bowl",
        "lemon",
        "punch",
        "parked truck",
        "chopped corn",
        "study work",
        "stockings",
    ]


@pytest.fixture
def vad_processor():
    """Create a VAD processor for testing."""
    from ears.audio.vad_processor import create_vad_processor
    return create_vad_processor(min_silence_duration_ms=600)
