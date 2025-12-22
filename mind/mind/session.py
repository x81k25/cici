# standard library imports
from dataclasses import dataclass, field
from datetime import datetime

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
    Internal session state.

    Maintains the single persistent session that tracks
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
        """Initialize tmux session and logging after dataclass init."""
        if self.tmux is None:
            # create tmux session with timestamp prefix for cleanup
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            tmux_name = f"{timestamp}_{self.id}"
            self.tmux = TmuxSession(tmux_name)

        # create logging session
        create_log_session(self.id)

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
        logger.info(f"session {self.id} cleaned up")

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
