# standard library imports
import asyncio
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


# ------------------------------------------------------------------------------
# fixtures
# ------------------------------------------------------------------------------

@pytest_asyncio.fixture
async def session():
    """Create a session for testing."""
    from mind.session import Session
    session = Session(id="test")
    yield session
    # cleanup
    session.cleanup()


@pytest.fixture
def input_processor():
    """Create an InputProcessor for testing."""
    from mind.input_processor import InputProcessor
    return InputProcessor()


@pytest.fixture
def command_router():
    """Create a CommandRouter for testing."""
    from mind.command_router import CommandRouter
    return CommandRouter()


@pytest.fixture
def cli_controller():
    """Create a CLIController for testing."""
    from mind.controllers.cli import CLIController
    return CLIController()


@pytest.fixture
def ollama_controller():
    """Create an OllamaController for testing."""
    from mind.controllers.ollama import OllamaController
    return OllamaController()


@pytest.fixture
def transcript_buffer():
    """Create a TranscriptBuffer for testing."""
    from mind.transcript_buffer import TranscriptBuffer
    return TranscriptBuffer()


@pytest.fixture
def message_buffer():
    """Create a MessageBuffer for testing."""
    from mind.message_buffer import MessageBuffer
    return MessageBuffer()


@pytest.fixture
def mock_tmux_session():
    """Create a mock TmuxSession."""
    from unittest.mock import MagicMock
    tmux = MagicMock()
    tmux.session_name = "test_session"
    tmux.exists.return_value = True
    tmux.create.return_value = True
    tmux.execute.return_value = "mock output"
    tmux.kill.return_value = True
    return tmux
