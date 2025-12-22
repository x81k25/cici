"""Thread-safe queue manager for TTS synthesis pipeline."""

import threading
from collections import deque
from typing import Optional
from dataclasses import dataclass

from app.config import settings
from app.models import QueueItem


@dataclass
class AudioChunk:
    """Completed audio chunk ready for delivery."""

    audio_data: bytes
    text: str
    request_id: Optional[str] = None


class QueueManager:
    """
    Manages the TTS synthesis pipeline queues.

    - Pending queue: FIFO with max depth, drops oldest on overflow
    - Completed buffer: Holds synthesized audio chunks in order
    """

    def __init__(self, max_depth: int = settings.max_queue_depth):
        self._max_depth = max_depth
        self._pending: deque[QueueItem] = deque()
        self._completed: deque[AudioChunk] = deque()
        self._lock = threading.Lock()
        self._item_available = threading.Event()

    def push_pending(self, item: QueueItem) -> tuple[int, bool]:
        """
        Add item to pending queue.

        Returns:
            Tuple of (queue_position, was_dropped) where was_dropped indicates
            if an older item was dropped to make room.
        """
        with self._lock:
            dropped = False
            if len(self._pending) >= self._max_depth:
                self._pending.popleft()
                dropped = True

            self._pending.append(item)
            position = len(self._pending)
            self._item_available.set()

            return position, dropped

    def pop_pending(self, timeout: Optional[float] = None) -> Optional[QueueItem]:
        """
        Remove and return the next item from pending queue.

        Args:
            timeout: How long to wait for an item (None = block forever)

        Returns:
            QueueItem or None if timeout expires with no item
        """
        while True:
            with self._lock:
                if self._pending:
                    item = self._pending.popleft()
                    if not self._pending:
                        self._item_available.clear()
                    return item

            # Wait for an item to be available
            if not self._item_available.wait(timeout=timeout):
                return None

    def push_completed(self, chunk: AudioChunk) -> None:
        """Add completed audio chunk to the buffer."""
        with self._lock:
            self._completed.append(chunk)

    def pop_completed(self) -> Optional[AudioChunk]:
        """Remove and return the next completed audio chunk, or None if empty."""
        with self._lock:
            if self._completed:
                return self._completed.popleft()
            return None

    def pending_count(self) -> int:
        """Return number of items in pending queue."""
        with self._lock:
            return len(self._pending)

    def completed_count(self) -> int:
        """Return number of items in completed buffer."""
        with self._lock:
            return len(self._completed)

    def clear_all(self) -> None:
        """Clear both queues (for shutdown)."""
        with self._lock:
            self._pending.clear()
            self._completed.clear()
            self._item_available.clear()


# Global queue manager instance
queue_manager = QueueManager()
