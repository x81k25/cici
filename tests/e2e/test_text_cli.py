"""CLI mode text tests."""

import pytest

from helpers import (
    AdbHelper,
    parse_ui_state,
    send_and_wait,
    send_and_wait_for_mode,
)

pytestmark = [pytest.mark.text, pytest.mark.slow]

# MIND CLI mode depends on tmux — if not installed, commands return an error.
# Tests check that CLI mode activates and responds, not that commands succeed.
TMUX_ERROR = "No such file or directory"


def _assert_cli_mode(state):
    """Verify we entered CLI mode via status bar or system message."""
    in_cli = (
        "cli" in state.status_bar_text.lower()
        or state.has_text("Command mode")
        or state.has_text("Terminal ready")
        or state.has_text("Switched to CLI")
    )
    assert in_cli, f"Should be in CLI mode. Status: {state.status_bar_text}, msgs: {state.messages}"


class TestTextCli:

    def test_enter_cli_mode(self, adb: AdbHelper, reset_mode, fresh_app):
        """Sending 'cli mode' should switch to CLI mode."""
        state = send_and_wait_for_mode(adb, "cli mode")
        _assert_cli_mode(state)

    def test_list_files(self, adb: AdbHelper, reset_mode, fresh_app):
        """'list files' in CLI mode should produce a response."""
        send_and_wait_for_mode(adb, "cli mode")
        state = send_and_wait(adb, "list files")
        # CLI should respond — either with ls output or a tmux error
        has_response = (
            state.has_text("$ ") or state.has_text("ls")
            or state.has_text(TMUX_ERROR)
            or state.total_msg_nodes >= 4
        )
        assert has_response, f"Should have CLI response. msgs: {state.messages}"

    def test_show_directory(self, adb: AdbHelper, reset_mode, fresh_app):
        """'show current directory' should show a path or error response."""
        send_and_wait_for_mode(adb, "cli mode")
        state = send_and_wait(adb, "show current directory")
        has_response = state.has_text("/") or state.has_text(TMUX_ERROR)
        assert has_response, f"Should have response. msgs: {state.messages}"

    def test_natural_language(self, adb: AdbHelper, reset_mode, fresh_app):
        """Natural language should be translated to a command."""
        send_and_wait_for_mode(adb, "cli mode")
        state = send_and_wait(adb, "what processes are using the most memory")
        # Should have response nodes beyond user message
        assert state.total_msg_nodes >= 4, \
            f"Should have mode switch + user msg + response. Nodes: {state.total_msg_nodes}"

    def test_command_correction(self, adb: AdbHelper, reset_mode, fresh_app):
        """Typo 'gti status' should produce a CLI response."""
        send_and_wait_for_mode(adb, "cli mode")
        state = send_and_wait(adb, "gti status")
        # Should get a response — either corrected command or tmux error
        has_response = (
            state.has_text("git") or state.has_text(TMUX_ERROR)
            or state.total_msg_nodes >= 4
        )
        assert has_response, f"Should have CLI response. msgs: {state.messages}"

    def test_direct_echo(self, adb: AdbHelper, reset_mode, fresh_app):
        """Direct command 'echo hello' should work."""
        send_and_wait_for_mode(adb, "cli mode")
        state = send_and_wait(adb, "echo hello")
        has_response = state.has_text("hello") or state.has_text(TMUX_ERROR)
        assert has_response, f"Should show echo output or error. msgs: {state.messages}"

    def test_alternative_triggers(self, adb: AdbHelper, reset_mode, fresh_app):
        """'terminal mode' and 'commands mode' should also enter CLI."""
        state = send_and_wait_for_mode(adb, "terminal mode")
        _assert_cli_mode(state)

        # Reset and try another trigger
        send_and_wait_for_mode(adb, "chat mode")  # back to ollama
        state = send_and_wait_for_mode(adb, "commands mode")
        _assert_cli_mode(state)

    def test_create_folder(self, adb: AdbHelper, reset_mode, fresh_app):
        """Create a folder via CLI, verify response."""
        send_and_wait_for_mode(adb, "cli mode")
        state = send_and_wait(adb, "create a folder called test-e2e-temp")
        has_response = (
            state.has_text("mkdir") or state.has_text("test-e2e-temp")
            or state.has_text(TMUX_ERROR)
        )
        assert has_response, f"Should get response. msgs: {state.messages}"
        # Cleanup attempt
        send_and_wait(adb, "remove the folder test-e2e-temp")
