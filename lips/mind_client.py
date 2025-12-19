"""HTTP client for MIND REST API communication."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import httpx


class ConnectionState(Enum):
    """Connection states."""
    DISCONNECTED = "disconnected"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class MindClient:
    """HTTP client for MIND REST API.

    Manages session lifecycle and text processing via REST API.
    """

    base_url: str = "http://localhost:8765"
    session_id: str | None = None
    mode: str = "ollama"  # interaction mode: ollama, cli, claude_code
    current_directory: str | None = None
    state: ConnectionState = ConnectionState.DISCONNECTED
    error_message: str | None = None

    # Response history for UI
    responses: list[dict] = field(default_factory=list)

    def create_session(self) -> bool:
        """Create a new session.

        Returns:
            True if session created successfully, False otherwise.
        """
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(f"{self.base_url}/sessions")
                if resp.status_code == 200:
                    data = resp.json()
                    self.session_id = data.get("session_id")
                    self.mode = data.get("mode", "ollama")
                    self.current_directory = data.get("current_directory")
                    self.state = ConnectionState.CONNECTED
                    self.error_message = None
                    return True
                elif resp.status_code == 503:
                    # Max sessions reached
                    data = resp.json()
                    self.error_message = data.get("detail", {}).get("message", "Max sessions reached")
                    self.state = ConnectionState.ERROR
                    return False
                else:
                    self.error_message = f"Failed to create session: {resp.status_code}"
                    self.state = ConnectionState.ERROR
                    return False
        except Exception as e:
            self.error_message = str(e)
            self.state = ConnectionState.ERROR
            return False

    def get_session(self, session_id: str) -> dict | None:
        """Get session info.

        Args:
            session_id: Session ID to get info for.

        Returns:
            Session info dict, or None if not found.
        """
        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.get(f"{self.base_url}/sessions/{session_id}")
                if resp.status_code == 200:
                    return resp.json()
        except Exception:
            pass
        return None

    def join_session(self, session_id: str) -> bool:
        """Join an existing session.

        Args:
            session_id: Session ID to join.

        Returns:
            True if joined successfully, False otherwise.
        """
        session_info = self.get_session(session_id)
        if session_info:
            self.session_id = session_info.get("session_id")
            self.mode = session_info.get("mode", "ollama")
            self.current_directory = session_info.get("current_directory")
            self.state = ConnectionState.CONNECTED
            self.error_message = None
            return True
        else:
            self.error_message = f"Session {session_id} not found"
            self.state = ConnectionState.ERROR
            return False

    def disconnect(self, kill_session: bool = False) -> None:
        """Disconnect from session.

        Args:
            kill_session: If True, also kills the session on server.
        """
        if kill_session and self.session_id:
            self.kill_session(self.session_id)

        self.session_id = None
        self.state = ConnectionState.DISCONNECTED
        self.error_message = None
        self.responses = []

    def process_text(self, text: str, original_voice: str | None = None) -> dict | None:
        """Send text for processing.

        Args:
            text: Text to process.
            original_voice: Optional original voice transcription.

        Returns:
            Response dict, or None if failed.
        """
        if not self.session_id:
            self.error_message = "No active session"
            return None

        try:
            payload = {"text": text}
            if original_voice:
                payload["original_voice"] = original_voice

            with httpx.Client(timeout=120.0) as client:  # Long timeout for Claude Code
                resp = client.post(
                    f"{self.base_url}/sessions/{self.session_id}/process",
                    json=payload
                )
                if resp.status_code == 200:
                    data = resp.json()
                    # Update local state from response
                    self.mode = data.get("mode", self.mode)
                    self.current_directory = data.get("current_directory", self.current_directory)
                    # Add to response history
                    self.responses.append(data)
                    return data
                elif resp.status_code == 404:
                    self.error_message = "Session not found"
                    self.state = ConnectionState.ERROR
                    return None
                else:
                    data = resp.json()
                    self.error_message = data.get("detail", {}).get("message", f"Error: {resp.status_code}")
                    return None
        except httpx.TimeoutException:
            self.error_message = "Request timed out"
            return None
        except Exception as e:
            self.error_message = str(e)
            return None

    def cancel_tasks(self) -> bool:
        """Cancel active tasks for current session.

        Returns:
            True if cancelled successfully, False otherwise.
        """
        if not self.session_id:
            return False

        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.post(f"{self.base_url}/sessions/{self.session_id}/cancel")
                return resp.status_code == 200
        except Exception:
            return False

    def list_sessions(self) -> list[dict]:
        """List all active sessions.

        Returns:
            List of session info dicts.
        """
        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.get(f"{self.base_url}/sessions")
                if resp.status_code == 200:
                    return resp.json()
        except Exception:
            pass
        return []

    def kill_session(self, session_id: str) -> bool:
        """Kill a specific session.

        Args:
            session_id: Session ID to kill.

        Returns:
            True if killed successfully, False otherwise.
        """
        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.delete(f"{self.base_url}/sessions/{session_id}")
                return resp.status_code == 200
        except Exception:
            return False

    def kill_all_sessions(self) -> int:
        """Kill all sessions.

        Returns:
            Number of sessions killed.
        """
        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.delete(f"{self.base_url}/sessions")
                if resp.status_code == 200:
                    return resp.json().get("killed", 0)
        except Exception:
            pass
        return 0

    def health_check(self) -> bool:
        """Check if MIND server is healthy.

        Returns:
            True if server is healthy, False otherwise.
        """
        try:
            with httpx.Client(timeout=2.0) as client:
                resp = client.get(f"{self.base_url}/health")
                return resp.status_code == 200
        except Exception:
            return False

    def get_responses(self) -> list[dict]:
        """Get and clear response history.

        Returns:
            List of response dicts.
        """
        responses = self.responses.copy()
        self.responses = []
        return responses
