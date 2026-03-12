"""Claude Code mode text tests."""

import pytest

from helpers import (
    AdbHelper,
    send_and_wait,
    send_and_wait_for_mode,
)

pytestmark = [pytest.mark.text, pytest.mark.slow]


def _assert_code_mode(state):
    """Verify we entered Claude Code mode via status bar or system message."""
    in_code = (
        "claude_code" in state.status_bar_text.lower()
        or state.has_text("code mode")
        or state.has_text("Entering code mode")
        or state.has_text("Switched to Claude Code")
    )
    assert in_code, f"Should be in code mode. Status: {state.status_bar_text}, msgs: {state.messages}"


class TestTextClaudeCode:

    def test_enter_code_mode(self, adb: AdbHelper, reset_mode, fresh_app):
        """'code mode' should switch to Claude Code mode."""
        state = send_and_wait_for_mode(adb, "code mode")
        _assert_code_mode(state)

    def test_read_file(self, adb: AdbHelper, reset_mode, fresh_app):
        """Reading a file should return a claude-code response."""
        send_and_wait_for_mode(adb, "code mode")
        state = send_and_wait(adb, "read the main.py file in the mind directory")
        # Response may have [claude-code] tag or just be in code mode
        has_response = (
            state.has_text("[claude-code]")
            or state.total_msg_nodes >= 4  # mode + user + response nodes
        )
        assert has_response, f"Should get a response. Nodes: {state.total_msg_nodes}, msgs: {state.messages}"

    def test_follow_up(self, adb: AdbHelper, reset_mode, fresh_app):
        """Follow-up question after file read should work."""
        send_and_wait_for_mode(adb, "code mode")
        send_and_wait(adb, "read the main.py file in the mind directory")
        state = send_and_wait(adb, "what functions are defined there")
        # At minimum we should have several message nodes
        assert state.total_msg_nodes >= 5, f"Should have multiple responses. Nodes: {state.total_msg_nodes}"
        assert "claude_code" in state.status_bar_text.lower(), "Should still be in code mode"

    def test_alternative_triggers(self, adb: AdbHelper, reset_mode, fresh_app):
        """'let's code' and 'coding mode' should enter Claude Code mode."""
        state = send_and_wait_for_mode(adb, "lets code")
        _assert_code_mode(state)

        send_and_wait_for_mode(adb, "ollama mode")  # reset
        state = send_and_wait_for_mode(adb, "coding mode")
        _assert_code_mode(state)

    def test_confirmation_negative(self, adb: AdbHelper, reset_mode, fresh_app):
        """Declining a destructive request should not crash."""
        send_and_wait_for_mode(adb, "code mode")
        send_and_wait(adb, "delete all pyc files in the project")
        state = send_and_wait(adb, "negative")
        assert adb.is_app_foreground(), "App should survive confirmation decline"
        assert state.total_msg_nodes >= 5, "Should have responses to both messages"
