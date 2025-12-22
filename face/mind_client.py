"""HTTP client for MIND REST API communication.

MIND uses a stateless REST API with internal session management.
FACE sends text via POST /text and polls for responses via GET /messages.
"""

from dataclasses import dataclass, field
from enum import Enum

import httpx


class ConnectionState(Enum):
    """Connection states."""
    DISCONNECTED = "disconnected"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class MindClient:
    """HTTP client for MIND REST API.

    MIND manages sessions internally. This client simply sends text
    and polls for messages. Connection state reflects server availability.
    """

    base_url: str = "http://localhost:8765"
    mode: str = "ollama"  # interaction mode: ollama, cli, claude_code
    current_directory: str = "/infra/experiments/cici"
    state: ConnectionState = ConnectionState.DISCONNECTED
    error_message: str | None = None

    # Response history for UI
    responses: list[dict] = field(default_factory=list)

    def connect(self) -> bool:
        """Connect to the MIND server.

        Verifies server is available and gets initial state.

        Returns:
            True if connected successfully, False otherwise.
        """
        try:
            with httpx.Client(timeout=5.0) as client:
                # Health check
                resp = client.get(f"{self.base_url}/health")
                if resp.status_code == 200:
                    data = resp.json()
                    self.mode = data.get("mode", "ollama")
                    self.state = ConnectionState.CONNECTED
                    self.error_message = None
                    return True
                else:
                    self.error_message = f"Server returned {resp.status_code}"
                    self.state = ConnectionState.ERROR
                    return False
        except httpx.ConnectError:
            self.error_message = "Cannot connect to server"
            self.state = ConnectionState.ERROR
            return False
        except Exception as e:
            self.error_message = str(e)
            self.state = ConnectionState.ERROR
            return False

    def disconnect(self) -> None:
        """Disconnect from server."""
        self.state = ConnectionState.DISCONNECTED
        self.error_message = None
        self.responses = []

    def process_text(self, text: str, original_voice: str | None = None) -> dict | None:
        """Send text for processing.

        Args:
            text: Text to process.
            original_voice: Optional original voice transcription.

        Returns:
            Response dict with messages, mode, and current_directory, or None if failed.
        """
        if self.state != ConnectionState.CONNECTED:
            self.error_message = "Not connected to server"
            return None

        try:
            payload = {"text": text}
            if original_voice:
                payload["original_voice"] = original_voice

            with httpx.Client(timeout=120.0) as client:  # Long timeout for LLM responses
                # Send text
                resp = client.post(f"{self.base_url}/text", json=payload)
                if resp.status_code != 200:
                    data = resp.json()
                    self.error_message = data.get("detail", {}).get("message", f"Error: {resp.status_code}")
                    return None

                # Poll for messages
                msg_resp = client.get(f"{self.base_url}/messages")
                if msg_resp.status_code == 200:
                    data = msg_resp.json()
                    # Update local state from response
                    self.mode = data.get("mode", self.mode)
                    self.current_directory = data.get("current_directory", self.current_directory)
                    # Add to response history
                    self.responses.append(data)
                    return data
                else:
                    self.error_message = f"Failed to get messages: {msg_resp.status_code}"
                    return None

        except httpx.TimeoutException:
            self.error_message = "Request timed out"
            return None
        except httpx.ConnectError:
            self.error_message = "Connection lost"
            self.state = ConnectionState.ERROR
            return None
        except Exception as e:
            self.error_message = str(e)
            return None

    def poll_messages(self) -> dict | None:
        """Poll for new messages without sending text.

        Returns:
            Response dict with messages, mode, and current_directory, or None if failed.
        """
        if self.state != ConnectionState.CONNECTED:
            return None

        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.get(f"{self.base_url}/messages")
                if resp.status_code == 200:
                    data = resp.json()
                    self.mode = data.get("mode", self.mode)
                    self.current_directory = data.get("current_directory", self.current_directory)
                    return data
                return None
        except Exception:
            return None

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
