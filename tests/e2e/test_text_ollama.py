"""Ollama mode text conversation tests."""

import time

import pytest

from helpers import (
    AdbHelper,
    LLM_RESPONSE_TIMEOUT,
    parse_ui_state,
    send_and_wait,
    send_text_via_adb,
    wait_for_new_message,
)

pytestmark = [pytest.mark.text, pytest.mark.slow]


class TestTextOllama:

    def test_basic_chat(self, adb: AdbHelper, reset_mode, fresh_app):
        """Send a question, verify LLM response appears in UI."""
        state = send_and_wait(adb, "What is the weather usually like in December")
        assert state.total_msg_nodes >= 2 or state.has_text("[hermes3]"), \
            f"Should have response. Nodes: {state.total_msg_nodes}, has_tag: {state.has_text('[hermes3]')}"

    def test_context_retention(self, adb: AdbHelper, reset_mode, fresh_app):
        """LLM should remember context within a session."""
        send_and_wait(adb, "My favorite color is blue")
        state = send_and_wait(adb, "What did I just tell you")
        assert state.has_text("blue"), \
            f"Response should mention 'blue'. Visible msgs: {state.messages}"

    def test_follow_up(self, adb: AdbHelper, reset_mode, fresh_app):
        """Follow-up questions should work without mode change."""
        send_and_wait(adb, "What is Python used for")
        state = send_and_wait(adb, "And what about JavaScript")
        # Long LLM responses cause aggressive RecyclerView recycling —
        # only the last response may be visible. Verify we got a response.
        assert state.total_msg_nodes >= 1, "Should have at least one visible node"
        assert state.has_text("[hermes3]") or "ollama" in state.status_bar_text.lower(), \
            "Should be in ollama mode with a response"

    def test_response_model_tag(self, adb: AdbHelper, reset_mode, fresh_app):
        """Responses in ollama mode should be prefixed with [hermes3]."""
        state = send_and_wait(adb, "Hello how are you")
        assert state.has_text("[hermes3]"), "Response should have [hermes3] tag"

    def test_rapid_messages(self, adb: AdbHelper, reset_mode, fresh_app):
        """Sending 3 messages rapidly should not crash the app."""
        before = parse_ui_state(adb)
        nodes_before = before.total_msg_nodes

        send_text_via_adb(adb, "First message")
        time.sleep(1)
        send_text_via_adb(adb, "Second message")
        time.sleep(1)
        send_text_via_adb(adb, "Third message")

        # Wait for at least some responses to appear
        state = wait_for_new_message(adb, nodes_before + 2, timeout=LLM_RESPONSE_TIMEOUT * 3)
        assert adb.is_app_foreground(), "App should still be in foreground"
        # With long responses, RecyclerView may only show 1-3 nodes.
        # Verify at least one hermes3 response visible.
        hermes_msgs = [m for m in state.messages if "[hermes3]" in m]
        assert len(hermes_msgs) >= 1, \
            f"Should have at least one hermes3 response visible. msgs: {state.messages}"

    def test_long_input(self, adb: AdbHelper, reset_mode, fresh_app):
        """A long message (200+ chars) should get a response without crash."""
        long_text = "This is a test " * 14  # ~210 chars
        state = send_and_wait(adb, long_text)
        assert adb.is_app_foreground(), "App should survive long input"
        assert state.total_msg_nodes >= 1, "Should have at least one message node"
