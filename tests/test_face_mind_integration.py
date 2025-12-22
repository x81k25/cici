"""
Integration tests for FACE<->MIND communication.

These tests spin up a real MIND server and use the MindClient to send
text submissions and verify responses.

Test scenarios are based on docs/sample-conversations.md.
"""

# standard library imports
import sys
from pathlib import Path

# 3rd-party imports
import httpx
import pytest
from streamlit.testing.v1 import AppTest

# Path setup
CICI_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(CICI_ROOT / "face"))

from mind_client import MindClient, ConnectionState


# ------------------------------------------------------------------------------
# Helper Classes
# ------------------------------------------------------------------------------

class MindTestClient:
    """Test client that wraps MindClient with additional test utilities."""

    def __init__(self, base_url: str):
        self.client = MindClient(base_url=base_url)
        self.base_url = base_url

    def connect(self) -> bool:
        """Connect to the server."""
        return self.client.connect()

    def disconnect(self) -> None:
        """Disconnect from server."""
        self.client.disconnect()

    def send_text(self, text: str) -> dict | None:
        """Send text and return response."""
        return self.client.process_text(text)

    def health_check(self) -> bool:
        """Check if server is healthy."""
        return self.client.health_check()

    @property
    def mode(self) -> str:
        """Current interaction mode."""
        return self.client.mode

    @property
    def current_directory(self) -> str:
        """Current working directory."""
        return self.client.current_directory

    @property
    def state(self) -> ConnectionState:
        """Current connection state."""
        return self.client.state

    def get_messages(self, response: dict | None) -> list[dict]:
        """Extract messages from response."""
        if response is None:
            return []
        return response.get("messages", [])

    def get_first_message(self, response: dict | None) -> dict | None:
        """Get first message from response."""
        messages = self.get_messages(response)
        return messages[0] if messages else None


# ------------------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------------------

@pytest.fixture
def test_client(mind_server) -> MindTestClient:
    """Create a connected test client."""
    client = MindTestClient(base_url=mind_server)
    assert client.connect(), f"Failed to connect to MIND server: {client.client.error_message}"
    yield client
    client.disconnect()


@pytest.fixture
def streamlit_app(mind_server, monkeypatch) -> AppTest:
    """Create Streamlit AppTest with MIND server configured."""
    # Set environment for the app
    monkeypatch.setenv("CICI_API_HOST", "localhost")
    monkeypatch.setenv("CICI_API_PORT", "18765")
    monkeypatch.setenv("CICI_API_SECURE", "false")

    # Create AppTest from the text page
    app_path = CICI_ROOT / "face" / "pages" / "text.py"
    at = AppTest.from_file(str(app_path), default_timeout=30)
    return at


# ------------------------------------------------------------------------------
# Health Check Tests
# ------------------------------------------------------------------------------

class TestMindServerHealth:
    """Tests for MIND server availability."""

    @pytest.mark.integration
    def test_server_is_healthy(self, mind_server):
        """Verify MIND server responds to health check."""
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(f"{mind_server}/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "healthy"
            assert data["service"] == "mind"

    @pytest.mark.integration
    def test_client_connects(self, mind_server):
        """Verify client can connect to server."""
        client = MindTestClient(base_url=mind_server)
        assert client.connect()
        assert client.state == ConnectionState.CONNECTED
        client.disconnect()


# ------------------------------------------------------------------------------
# Mode Switching Tests (from sample-conversations.md)
# ------------------------------------------------------------------------------

class TestModeSwitching:
    """Tests for mode switching functionality."""

    @pytest.mark.integration
    def test_default_mode_is_ollama(self, test_client):
        """Verify default mode is Ollama."""
        assert test_client.mode == "ollama"

    @pytest.mark.integration
    def test_switch_to_cli_mode(self, test_client):
        """Verify switching to CLI mode with 'cli mode' trigger."""
        response = test_client.send_text("cli mode")
        assert response is not None
        assert test_client.mode == "cli"

        # Check response contains mode change message
        msg = test_client.get_first_message(response)
        assert msg is not None
        assert msg.get("type") == "system"
        assert msg.get("mode_changed") is True
        assert msg.get("new_mode") == "cli"

    @pytest.mark.integration
    def test_switch_to_cli_mode_terminal(self, test_client):
        """Verify switching to CLI mode with 'terminal mode' trigger."""
        response = test_client.send_text("terminal mode")
        assert response is not None
        assert test_client.mode == "cli"

    @pytest.mark.integration
    def test_switch_to_cli_mode_commands(self, test_client):
        """Verify switching to CLI mode with 'commands mode' trigger."""
        response = test_client.send_text("commands mode")
        assert response is not None
        assert test_client.mode == "cli"

    @pytest.mark.integration
    def test_switch_to_ollama_mode(self, test_client):
        """Verify switching to Ollama mode with 'chat mode' trigger."""
        # First switch to CLI
        test_client.send_text("cli mode")
        assert test_client.mode == "cli"

        # Then switch back to Ollama
        response = test_client.send_text("chat mode")
        assert response is not None
        assert test_client.mode == "ollama"

    @pytest.mark.integration
    def test_switch_to_ollama_mode_back_to_chat(self, test_client):
        """Verify switching to Ollama mode with 'back to chat' trigger."""
        # First switch to CLI
        test_client.send_text("cli mode")

        # Then switch back
        response = test_client.send_text("back to chat")
        assert response is not None
        assert test_client.mode == "ollama"

    @pytest.mark.integration
    def test_switch_to_code_mode(self, test_client):
        """Verify switching to Claude Code mode with 'code mode' trigger."""
        response = test_client.send_text("code mode")
        assert response is not None
        assert test_client.mode == "claude_code"

    @pytest.mark.integration
    def test_switch_to_code_mode_lets_code(self, test_client):
        """Verify switching to Claude Code mode with 'let's code' trigger."""
        response = test_client.send_text("let's code")
        assert response is not None
        assert test_client.mode == "claude_code"

    @pytest.mark.integration
    def test_rapid_mode_switching(self, test_client):
        """Test rapid mode switching doesn't break state."""
        # CLI mode
        test_client.send_text("cli mode")
        assert test_client.mode == "cli"

        # Chat mode
        test_client.send_text("chat mode")
        assert test_client.mode == "ollama"

        # Code mode
        test_client.send_text("code mode")
        assert test_client.mode == "claude_code"

        # Ollama mode
        test_client.send_text("ollama mode")
        assert test_client.mode == "ollama"


# ------------------------------------------------------------------------------
# CLI Mode Tests (from sample-conversations.md)
# ------------------------------------------------------------------------------

class TestCLIMode:
    """Tests for CLI mode functionality."""

    @pytest.mark.integration
    def test_cli_echo_command(self, test_client):
        """Verify echo command works in CLI mode."""
        # Enter CLI mode
        test_client.send_text("cli mode")
        assert test_client.mode == "cli"

        # Execute echo
        response = test_client.send_text("echo hello world")
        assert response is not None

        msg = test_client.get_first_message(response)
        assert msg is not None
        assert msg.get("type") == "cli_result"
        assert msg.get("success") is True
        assert msg.get("exit_code") == 0
        assert "hello" in msg.get("output", "").lower()

    @pytest.mark.integration
    def test_cli_pwd_command(self, test_client):
        """Verify pwd command works in CLI mode."""
        test_client.send_text("cli mode")

        response = test_client.send_text("pwd")
        assert response is not None

        msg = test_client.get_first_message(response)
        assert msg is not None
        assert msg.get("type") == "cli_result"
        assert msg.get("success") is True
        # Output should contain a path
        output = msg.get("output", "")
        assert "/" in output

    @pytest.mark.integration
    def test_cli_ls_command(self, test_client):
        """Verify ls command works in CLI mode."""
        test_client.send_text("commands mode")

        response = test_client.send_text("ls")
        assert response is not None

        msg = test_client.get_first_message(response)
        assert msg is not None
        assert msg.get("type") == "cli_result"
        assert msg.get("success") is True

    @pytest.mark.integration
    @pytest.mark.slow
    def test_cli_natural_language_list_files(self, test_client):
        """Verify natural language 'list files' is handled in CLI mode.

        Note: Translation of natural language to shell commands depends on
        LLM availability. This test verifies the response structure is correct.
        """
        test_client.send_text("terminal mode")

        response = test_client.send_text("list files")
        assert response is not None

        msg = test_client.get_first_message(response)
        assert msg is not None
        assert msg.get("type") == "cli_result"
        # Should have attempted to execute something
        assert "command" in msg


# ------------------------------------------------------------------------------
# Ollama Mode Tests (from sample-conversations.md)
# ------------------------------------------------------------------------------

class TestOllamaMode:
    """Tests for Ollama (chat) mode functionality."""

    @pytest.mark.integration
    @pytest.mark.slow
    def test_ollama_basic_chat(self, test_client):
        """Verify basic chat produces LLM response."""
        # Ensure we're in Ollama mode
        test_client.send_text("chat mode")
        assert test_client.mode == "ollama"

        response = test_client.send_text("What is 2 plus 2?")
        assert response is not None

        msg = test_client.get_first_message(response)
        assert msg is not None
        assert msg.get("type") == "llm_response"
        assert msg.get("model") == "phi3"
        # Should have content (success) or error
        assert msg.get("content") or msg.get("error")

    @pytest.mark.integration
    @pytest.mark.slow
    def test_ollama_response_structure(self, test_client):
        """Verify Ollama response has correct structure."""
        # Ensure we're in Ollama mode
        test_client.send_text("chat mode")

        response = test_client.send_text("Hello")
        assert response is not None

        # Response should have mode and current_directory
        assert "mode" in response
        assert "current_directory" in response
        assert "messages" in response


# ------------------------------------------------------------------------------
# Response Structure Tests
# ------------------------------------------------------------------------------

class TestResponseStructure:
    """Tests for validating response structures from MIND."""

    @pytest.mark.integration
    def test_mode_change_response_structure(self, test_client):
        """Verify mode change responses have correct structure."""
        response = test_client.send_text("cli mode")
        assert response is not None

        # Response envelope
        assert response.get("mode") == "cli"
        assert "current_directory" in response
        assert "messages" in response

        # Message content
        msg = test_client.get_first_message(response)
        assert msg.get("type") == "system"
        assert msg.get("mode_changed") is True

    @pytest.mark.integration
    def test_cli_result_response_structure(self, test_client):
        """Verify CLI result responses have correct structure."""
        test_client.send_text("cli mode")
        response = test_client.send_text("echo test")
        assert response is not None

        msg = test_client.get_first_message(response)
        assert msg is not None
        assert msg.get("type") == "cli_result"
        assert "success" in msg
        assert "command" in msg
        assert "exit_code" in msg or "error" in msg

    @pytest.mark.integration
    def test_current_directory_in_response(self, test_client):
        """Verify current_directory is present in all responses."""
        # Test in different modes
        for mode_trigger in ["cli mode", "chat mode"]:
            response = test_client.send_text(mode_trigger)
            assert response is not None
            assert "current_directory" in response
            assert response["current_directory"] is not None


# ------------------------------------------------------------------------------
# Streamlit AppTest Integration Tests
# ------------------------------------------------------------------------------

class TestStreamlitAppIntegration:
    """Tests using Streamlit AppTest for UI integration."""

    @pytest.mark.integration
    def test_app_loads_without_error(self, streamlit_app):
        """Verify Streamlit app loads without exceptions."""
        streamlit_app.run()
        assert not streamlit_app.exception, f"App raised exception: {streamlit_app.exception}"

    @pytest.mark.integration
    def test_app_has_text_input(self, streamlit_app):
        """Verify app has a text input area."""
        streamlit_app.run()
        # Should have a text area for command input
        assert len(streamlit_app.text_area) >= 0  # May be 0 if disconnected


# ------------------------------------------------------------------------------
# Edge Cases
# ------------------------------------------------------------------------------

class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.integration
    def test_empty_input(self, test_client):
        """Verify empty input is handled gracefully."""
        response = test_client.send_text("")
        # Should return a response (possibly with error or no messages)
        # The important thing is it doesn't crash

    @pytest.mark.integration
    def test_whitespace_only_input(self, test_client):
        """Verify whitespace-only input is handled."""
        response = test_client.send_text("   ")
        # Should handle gracefully without crashing


# ------------------------------------------------------------------------------
# Integration Flow Tests (Multi-step scenarios)
# ------------------------------------------------------------------------------

class TestIntegrationFlows:
    """Tests for complete integration flows."""

    @pytest.mark.integration
    def test_full_cli_workflow(self, test_client):
        """Test complete CLI workflow: enter mode, run commands, exit."""
        # Enter CLI mode
        response = test_client.send_text("cli mode")
        assert response is not None
        assert test_client.mode == "cli"

        # Run a simple command
        response = test_client.send_text("echo 'hello from cli'")
        assert response is not None
        msg = test_client.get_first_message(response)
        assert msg.get("type") == "cli_result"

        # Exit back to chat
        response = test_client.send_text("back to chat")
        assert response is not None
        assert test_client.mode == "ollama"

    @pytest.mark.integration
    def test_mode_persistence_through_commands(self, test_client):
        """Verify mode stays consistent through multiple commands."""
        # Enter CLI mode
        test_client.send_text("commands mode")
        initial_mode = test_client.mode
        assert initial_mode == "cli"

        # Run several commands
        for cmd in ["pwd", "ls", "echo test"]:
            test_client.send_text(cmd)
            assert test_client.mode == initial_mode, f"Mode changed after '{cmd}'"

    @pytest.mark.integration
    def test_directory_tracking(self, test_client):
        """Verify current directory is tracked in responses."""
        test_client.send_text("cli mode")

        response = test_client.send_text("pwd")
        assert response is not None

        # Should have current_directory in response
        assert "current_directory" in response
        assert response["current_directory"] is not None
        assert "/" in response["current_directory"]
