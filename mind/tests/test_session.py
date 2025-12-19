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
        assert len(session.id) == 8
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


# ------------------------------------------------------------------------------
# SessionManager tests
# ------------------------------------------------------------------------------

class TestSessionManager:
    """Tests for the SessionManager class."""

    @pytest.mark.asyncio
    async def test_create_session(self, session_manager):
        """Test creating a new session."""
        session = await session_manager.create_session()

        assert session is not None
        assert session.id in session_manager.sessions
        assert session_manager.count == 1

    @pytest.mark.asyncio
    async def test_max_sessions_limit(self, session_manager):
        """Test that max sessions limit is enforced."""
        sessions = []

        # create max sessions
        for i in range(session_manager.max_sessions):
            session = await session_manager.create_session()
            sessions.append(session)
            assert session is not None

        # try to create one more
        session = await session_manager.create_session()

        assert session is None
        assert session_manager.count == session_manager.max_sessions

    @pytest.mark.asyncio
    async def test_get_session(self, session_manager):
        """Test getting a session by ID."""
        session = await session_manager.create_session()
        retrieved = await session_manager.get_session(session.id)

        assert retrieved is session

    @pytest.mark.asyncio
    async def test_get_nonexistent_session(self, session_manager):
        """Test getting a session that doesn't exist."""
        session = await session_manager.get_session("nonexistent")
        assert session is None

    @pytest.mark.asyncio
    async def test_remove_session(self, session_manager):
        """Test removing a session."""
        session = await session_manager.create_session()
        session_id = session.id

        result = await session_manager.remove_session(session_id)

        assert result is True
        assert session_id not in session_manager.sessions
        assert session_manager.count == 0

    @pytest.mark.asyncio
    async def test_remove_nonexistent_session(self, session_manager):
        """Test removing a session that doesn't exist."""
        result = await session_manager.remove_session("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_list_sessions(self, session_manager):
        """Test listing all sessions."""
        session1 = await session_manager.create_session()
        session2 = await session_manager.create_session()

        sessions = await session_manager.list_sessions()

        assert len(sessions) == 2
        session_ids = [s["session_id"] for s in sessions]
        assert session1.id in session_ids
        assert session2.id in session_ids
