# standard library imports
import asyncio
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# 3rd-party imports
from loguru import logger

# local imports
from mind.core.tmux_session import TmuxSession
from mind.core.session_logger import (
    create_session as create_log_session,
    remove_session as remove_log_session,
    get_session_logger,
)


@dataclass
class Session:
    """
    Per-request session state.

    Each API session gets its own Session instance that tracks
    conversation state, mode, and active tasks.
    """
    id: str
    interaction_mode: str = "ollama"  # "ollama" (default) | "cli" | "claude_code"
    conversation_context: list = field(default_factory=list)
    active_tasks: list = field(default_factory=list)
    message_history: list = field(default_factory=list)
    tmux: TmuxSession = field(default=None)
    current_directory: str = field(default="/infra/experiments/cici")
    created_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        """Initialize tmux session after dataclass init."""
        if self.tmux is None:
            # create tmux session with timestamp prefix for cleanup
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            tmux_name = f"{timestamp}_{self.id}"
            self.tmux = TmuxSession(tmux_name)

    @property
    def logger(self):
        """Get the logger bound to this session."""
        return get_session_logger(self.id)

    def update_activity(self) -> None:
        """Update the last activity timestamp."""
        self.last_activity = datetime.now()

    def add_to_context(self, role: str, content: str) -> None:
        """Add a message to the conversation context."""
        self.conversation_context.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })
        # keep only last 50 messages
        if len(self.conversation_context) > 50:
            self.conversation_context = self.conversation_context[-50:]

    def enter_ollama_mode(self) -> None:
        """Enter Ollama interaction mode (default mode)."""
        self.interaction_mode = "ollama"
        self.logger.info("entered Ollama mode")

    def exit_ollama_mode(self) -> None:
        """Exit Ollama mode, enter CLI commands mode."""
        self.interaction_mode = "cli"
        self.logger.info("exited Ollama mode, entered CLI mode")

    def enter_cli_mode(self) -> None:
        """Enter CLI commands mode."""
        self.interaction_mode = "cli"
        self.logger.info("entered CLI commands mode")

    def exit_cli_mode(self) -> None:
        """Exit CLI mode, return to Ollama mode (default)."""
        self.interaction_mode = "ollama"
        self.logger.info("exited CLI mode, returned to Ollama mode")

    def enter_claude_code_mode(self) -> None:
        """Enter Claude Code mode."""
        self.interaction_mode = "claude_code"
        self.logger.info("entered Claude Code mode")

    def clear_ollama_context(self) -> None:
        """Clear the Ollama conversation context for a fresh start."""
        self.conversation_context = []
        self.logger.info("cleared Ollama conversation context")

    def update_directory(self, new_directory: str) -> None:
        """Update the current working directory."""
        if new_directory != self.current_directory:
            old_dir = self.current_directory
            self.current_directory = new_directory
            self.logger.info(f"directory changed: {old_dir} -> {new_directory}")

    def add_message(self, direction: str, message: dict) -> None:
        """Add a message to the history for client-side log restoration.

        Args:
            direction: "sent" or "recv"
            message: The message dict
        """
        self.message_history.append({
            "direction": direction,
            "message": message,
            "timestamp": datetime.now().isoformat()
        })
        # Keep only last 100 messages
        if len(self.message_history) > 100:
            self.message_history = self.message_history[-100:]

    def sync_directory_from_tmux(self) -> bool:
        """
        Sync current_directory with the tmux session's pwd.

        Returns:
            True if directory was successfully synced, False otherwise.
        """
        if not self.tmux or not self.tmux.created:
            return False

        try:
            result = self.tmux.execute_with_status("pwd")
            if result["success"] and result["output"]:
                pwd = result["output"].strip()
                # Get the last line (actual pwd) in case there are other lines
                pwd_lines = pwd.split('\n')
                actual_pwd = pwd_lines[-1].strip() if pwd_lines else pwd

                if actual_pwd and actual_pwd != self.current_directory:
                    self.update_directory(actual_pwd)
                    return True
            return False
        except Exception as e:
            self.logger.warning(f"failed to sync directory from tmux: {e}")
            return False

    async def cancel_active_tasks(self) -> int:
        """Cancel all active tasks for this session."""
        cancelled = 0
        for task in self.active_tasks:
            if not task.done():
                task.cancel()
                cancelled += 1
        self.active_tasks = [t for t in self.active_tasks if not t.done()]
        if cancelled:
            self.logger.info(f"cancelled {cancelled} active tasks")
        return cancelled

    def cleanup(self) -> None:
        """Clean up session resources."""
        # kill tmux session
        if self.tmux:
            self.tmux.kill()
        # remove logging handlers
        remove_log_session(self.id)
        self.logger.info(f"session {self.id} cleaned up")

    def to_dict(self) -> dict:
        """Convert session to dictionary for API responses."""
        return {
            "session_id": self.id,
            "mode": self.interaction_mode,
            "current_directory": self.current_directory,
            "created_at": self.created_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "idle_seconds": (datetime.now() - self.last_activity).total_seconds(),
        }


class SessionManager:
    """
    Manages all active sessions.

    Enforces maximum concurrent sessions and provides session lookup.
    """

    def __init__(self, max_sessions: int = 10, claude_code_controller=None):
        """
        Initialize the session manager.

        Args:
            max_sessions: Maximum number of concurrent sessions allowed.
            claude_code_controller: Optional ClaudeCodeController for cleanup.
        """
        self.sessions: dict[str, Session] = {}
        self.max_sessions = max_sessions
        self.claude_code_controller = claude_code_controller
        self._lock = asyncio.Lock()

    async def create_session(self) -> Session | None:
        """
        Create a new session.

        Returns:
            The new Session instance, or None if max sessions reached.
        """
        async with self._lock:
            if len(self.sessions) >= self.max_sessions:
                logger.warning(f"max sessions ({self.max_sessions}) reached, rejecting")
                return None

            # generate unique session ID
            session_id = str(uuid.uuid4())[:8]
            while session_id in self.sessions:
                session_id = str(uuid.uuid4())[:8]

            # create logging session
            create_log_session(session_id)

            # create session
            session = Session(id=session_id)

            self.sessions[session_id] = session
            logger.info(f"created session {session_id} ({len(self.sessions)}/{self.max_sessions})")

            return session

    async def get_session(self, session_id: str) -> Session | None:
        """Get a session by ID."""
        return self.sessions.get(session_id)

    async def remove_session(self, session_id: str) -> bool:
        """
        Remove a session and clean up its resources.

        Args:
            session_id: The session ID to remove.

        Returns:
            True if session was removed, False if not found.
        """
        async with self._lock:
            session = self.sessions.pop(session_id, None)
            if session:
                # cancel any active tasks
                await session.cancel_active_tasks()

                # clean up controller resources first
                if self.claude_code_controller:
                    try:
                        await self.claude_code_controller.cleanup_session(session)
                        logger.debug(f"cleaned up Claude Code controller for session {session_id}")
                    except Exception as e:
                        logger.warning(f"error cleaning up Claude Code controller for session {session_id}: {e}")

                # clean up session resources
                session.cleanup()
                logger.info(f"removed session {session_id} ({len(self.sessions)}/{self.max_sessions})")
                return True
            return False

    async def list_sessions(self) -> list[dict]:
        """List all sessions."""
        return [s.to_dict() for s in self.sessions.values()]

    async def cleanup_stale_sessions(self, max_idle_seconds: float = 3600.0) -> int:
        """
        Remove sessions that have been idle too long.

        Args:
            max_idle_seconds: Maximum idle time before session is removed.

        Returns:
            Number of sessions cleaned up.
        """
        now = datetime.now()
        to_remove = []

        async with self._lock:
            for session_id, session in self.sessions.items():
                idle_duration = (now - session.last_activity).total_seconds()
                if idle_duration > max_idle_seconds:
                    to_remove.append(session_id)

        # remove outside lock to avoid deadlock with remove_session
        cleaned = 0
        for session_id in to_remove:
            logger.info(f"cleaning up stale session {session_id}")
            await self.remove_session(session_id)
            cleaned += 1

        return cleaned

    @property
    def count(self) -> int:
        """Get the number of sessions."""
        return len(self.sessions)
