# standard library imports
import asyncio
from datetime import datetime
from typing import Any


class MessageBuffer:
    """
    Buffer for outgoing messages to FACE.

    Stores responses that FACE can poll via GET /messages.
    """

    def __init__(self):
        """Initialize the message buffer."""
        self._messages: list[dict[str, Any]] = []
        self._lock = asyncio.Lock()

    @property
    def count(self) -> int:
        """Get the number of buffered messages."""
        return len(self._messages)

    @property
    def is_empty(self) -> bool:
        """Check if buffer is empty."""
        return len(self._messages) == 0

    async def add(self, message: dict[str, Any]) -> None:
        """
        Add a message to the buffer.

        Args:
            message: The message dict to add.
        """
        async with self._lock:
            # add timestamp if not present
            if "timestamp" not in message:
                message["timestamp"] = datetime.now().isoformat()
            self._messages.append(message)

    async def get_and_clear(self) -> list[dict[str, Any]]:
        """
        Get all messages and clear the buffer.

        Returns:
            List of buffered messages.
        """
        async with self._lock:
            messages = self._messages.copy()
            self._messages = []
            return messages

    async def peek(self) -> list[dict[str, Any]]:
        """
        Get all messages without clearing the buffer.

        Returns:
            List of buffered messages (copy).
        """
        async with self._lock:
            return self._messages.copy()

    async def clear(self) -> int:
        """
        Clear the buffer.

        Returns:
            Number of messages cleared.
        """
        async with self._lock:
            count = len(self._messages)
            self._messages = []
            return count
