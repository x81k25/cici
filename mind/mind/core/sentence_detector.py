# standard library imports
import re
from typing import Optional


class SentenceBuffer:
    """Buffers streaming text and yields complete sentences."""

    SENTENCE_ENDINGS = re.compile(r'([.!?])\s+')

    def __init__(self):
        self.buffer = ""

    def add(self, chunk: str) -> list[str]:
        """
        Add a text chunk, return any complete sentences.

        Args:
            chunk: Incoming text chunk from LLM

        Returns:
            List of complete sentences (may be empty)
        """
        self.buffer += chunk
        sentences = []

        while True:
            match = self.SENTENCE_ENDINGS.search(self.buffer)
            if match:
                end_idx = match.end()
                sentence = self.buffer[:end_idx].strip()
                self.buffer = self.buffer[end_idx:]
                if sentence:
                    sentences.append(sentence)
            else:
                break

        return sentences

    def flush(self) -> Optional[str]:
        """Return any remaining text as final sentence."""
        remaining = self.buffer.strip()
        self.buffer = ""
        return remaining if remaining else None

    def clear(self) -> None:
        """Clear the buffer without returning content."""
        self.buffer = ""
