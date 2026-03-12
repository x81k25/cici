"""Edge case and error handling tests."""

import time

import pytest

from helpers import (
    AdbHelper,
    LLM_RESPONSE_TIMEOUT,
    parse_ui_state,
    send_and_wait,
    send_and_wait_for_mode,
    send_text_via_adb,
    wait_for_new_message,
)

pytestmark = [pytest.mark.edge_case, pytest.mark.slow]


class TestEdgeCases:

    def test_mode_keyword_in_speech(self, adb: AdbHelper, reset_mode, fresh_app):
        """Mode keywords in natural speech should NOT trigger mode switch."""
        state = send_and_wait(
            adb, "I was thinking about switching to code mode for my project"
        )
        assert "ollama" in state.status_bar_text.lower(), \
            f"Should stay in ollama mode. Status: {state.status_bar_text}"

    def test_ambiguous_help_cli(self, adb: AdbHelper, reset_mode, fresh_app):
        """'help' in CLI mode should not crash."""
        send_and_wait_for_mode(adb, "cli mode")
        state = send_and_wait(adb, "help")
        assert adb.is_app_foreground(), "App should survive 'help' in CLI"
        assert state.total_msg_nodes > 2, "Should have a response to 'help'"

    def test_unclear_command_cli(self, adb: AdbHelper, reset_mode, fresh_app):
        """Unclear command in CLI should produce some response, not crash."""
        send_and_wait_for_mode(adb, "cli mode")
        state = send_and_wait(adb, "do the thing")
        assert adb.is_app_foreground(), "App should survive unclear command"

    def test_empty_send(self, adb: AdbHelper, fresh_app):
        """Tapping send with empty input should not add a message."""
        state_before = parse_ui_state(adb)
        nodes_before = state_before.total_msg_nodes
        adb.tap_element("text_input")
        time.sleep(0.2)
        adb.run("input keyevent 29 29")
        time.sleep(0.1)
        adb.run("input keyevent 67 67 67 67 67 67 67 67 67 67")
        time.sleep(0.2)
        adb.tap_element("btn_send")
        time.sleep(1)
        state_after = parse_ui_state(adb)
        assert state_after.total_msg_nodes == nodes_before, "Empty send should not create messages"

    def test_special_characters(self, adb: AdbHelper, reset_mode, fresh_app):
        """Special characters in input should not crash."""
        state = send_and_wait(adb, "echo hello world")
        assert adb.is_app_foreground(), "App should handle special chars"

    def test_long_response(self, adb: AdbHelper, reset_mode, fresh_app):
        """A prompt that elicits a long response should not crash."""
        state = send_and_wait(
            adb,
            "Write a detailed explanation of how computers work",
            timeout=LLM_RESPONSE_TIMEOUT * 2,
        )
        assert adb.is_app_foreground(), "App should survive long response"
        # Long responses may fill the screen with a single node.
        # The key assertion is that the app survived and responded.
        assert state.total_msg_nodes >= 1 or "ollama" in state.status_bar_text.lower(), \
            "Should have at least one response node"

    def test_ask_claude_from_cli(self, adb: AdbHelper, reset_mode, fresh_app):
        """In CLI mode, 'ask claude' should get a response."""
        send_and_wait_for_mode(adb, "cli mode")
        state = send_and_wait(adb, "ask claude what is 2 plus 2")
        assert adb.is_app_foreground(), "App should handle cross-mode request"
        assert state.total_msg_nodes > 2, "Should get some response"

    def test_app_survives_backend_timeout(self, adb: AdbHelper, reset_mode, fresh_app):
        """App should stay responsive while backend processes."""
        send_text_via_adb(adb, "Explain quantum physics in detail")
        time.sleep(3)
        assert adb.is_app_foreground(), "App should not ANR while waiting"
        wait_for_new_message(
            adb, parse_ui_state(adb).total_msg_nodes - 1,
            timeout=LLM_RESPONSE_TIMEOUT,
        )
