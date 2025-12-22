# standard library imports
import asyncio
from unittest.mock import AsyncMock

# 3rd-party imports
import pytest


# ------------------------------------------------------------------------------
# Session tests
# ------------------------------------------------------------------------------

class TestSession:
    """Tests for the Session class."""

    @pytest.mark.asyncio
    async def test_session_creation(self, session):
        """Test that session is created with correct defaults."""
        assert session.id is not None
        assert session.id == "test"
        assert session.interaction_mode == "ollama"
        assert session.conversation_context == []
        assert session.active_tasks == []
        assert session.tmux is not None

    @pytest.mark.asyncio
    async def test_session_update_activity(self, session):
        """Test activity timestamp update."""
        from datetime import datetime
        import time

        initial_activity = session.last_activity
        time.sleep(0.01)  # small delay
        session.update_activity()

        assert session.last_activity > initial_activity

    @pytest.mark.asyncio
    async def test_session_add_to_context(self, session):
        """Test adding messages to conversation context."""
        session.add_to_context("user", "hello")
        session.add_to_context("assistant", "hi there")

        assert len(session.conversation_context) == 2
        assert session.conversation_context[0]["role"] == "user"
        assert session.conversation_context[0]["content"] == "hello"
        assert session.conversation_context[1]["role"] == "assistant"

    @pytest.mark.asyncio
    async def test_session_context_limit(self, session):
        """Test that conversation context is limited to 50 messages."""
        for i in range(60):
            session.add_to_context("user", f"message {i}")

        assert len(session.conversation_context) == 50
        # should keep the last 50
        assert session.conversation_context[0]["content"] == "message 10"

    @pytest.mark.asyncio
    async def test_session_cancel_active_tasks(self, session):
        """Test cancelling active tasks."""
        # create mock tasks
        async def dummy_task():
            await asyncio.sleep(10)

        task1 = asyncio.create_task(dummy_task())
        task2 = asyncio.create_task(dummy_task())
        session.active_tasks = [task1, task2]

        cancelled = await session.cancel_active_tasks()

        assert cancelled == 2
        # wait for tasks to process cancellation
        for task in [task1, task2]:
            try:
                await task
            except asyncio.CancelledError:
                pass
        assert task1.cancelled()
        assert task2.cancelled()

    @pytest.mark.asyncio
    async def test_session_mode_switching(self, session):
        """Test mode switching methods."""
        # start in ollama mode (default)
        assert session.interaction_mode == "ollama"

        # enter cli mode
        session.enter_cli_mode()
        assert session.interaction_mode == "cli"

        # enter claude code mode
        session.enter_claude_code_mode()
        assert session.interaction_mode == "claude_code"

        # back to ollama mode
        session.enter_ollama_mode()
        assert session.interaction_mode == "ollama"

    @pytest.mark.asyncio
    async def test_session_to_dict(self, session):
        """Test session serialization to dict."""
        data = session.to_dict()

        assert "session_id" in data
        assert data["session_id"] == session.id
        assert "mode" in data
        assert data["mode"] == session.interaction_mode
        assert "current_directory" in data
        assert "created_at" in data
        assert "last_activity" in data
        assert "idle_seconds" in data
