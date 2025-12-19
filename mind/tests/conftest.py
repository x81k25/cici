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
async def session_manager():
    """Create a fresh SessionManager for testing."""
    from mind.session import SessionManager
    from mind.controllers.claude_code import ClaudeCodeController
    claude_code_controller = ClaudeCodeController()
    manager = SessionManager(max_sessions=3, claude_code_controller=claude_code_controller)
    yield manager
    # cleanup all sessions
    for session_id in list(manager.sessions.keys()):
        await manager.remove_session(session_id)


@pytest_asyncio.fixture
async def session(session_manager):
    """Create a session for testing."""
    session = await session_manager.create_session()
    yield session
    # cleanup handled by session_manager fixture


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
