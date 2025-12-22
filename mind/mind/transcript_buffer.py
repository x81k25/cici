# standard library imports
import asyncio


class TranscriptBuffer:
    """
    Buffer for incoming words from EARS.

    Accumulates words until "execute" is received,
    then returns the full command and clears the buffer.
    """

    EXECUTE_TRIGGER = "execute"

    def __init__(self):
        """Initialize the transcript buffer."""
        self._words: list[str] = []
        self._lock = asyncio.Lock()

    @property
    def words(self) -> list[str]:
        """Get current buffered words (read-only copy)."""
        return self._words.copy()

    @property
    def is_empty(self) -> bool:
        """Check if buffer is empty."""
        return len(self._words) == 0

    def is_execute(self, word: str) -> bool:
        """Check if word is the execute trigger."""
        # strip whitespace and trailing punctuation
        cleaned = word.lower().strip().rstrip(".,!?;:")
        return cleaned == self.EXECUTE_TRIGGER

    async def add_word(self, word: str) -> dict:
        """
        Add a word to the buffer.

        Args:
            word: The word to add.

        Returns:
            Dict with buffer state:
            {
                "status": "buffered",
                "buffer": ["word1", "word2", ...]
            }
        """
        async with self._lock:
            cleaned = word.strip()
            if cleaned:
                self._words.append(cleaned)

            return {
                "status": "buffered",
                "buffer": self._words.copy()
            }

    async def get_and_clear(self) -> str:
        """
        Get the full command and clear the buffer.

        Returns:
            The buffered words joined with spaces.
        """
        async with self._lock:
            command = " ".join(self._words)
            self._words = []
            return command

    async def clear(self) -> None:
        """Clear the buffer without returning contents."""
        async with self._lock:
            self._words = []
