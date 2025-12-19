# standard library imports
from typing import TYPE_CHECKING

# 3rd-party imports
from loguru import logger

# local imports
from mind.core.translation import parse_voice_to_cli

if TYPE_CHECKING:
    from mind.session import Session


# stop words that trigger immediate cancellation
STOP_WORDS = [
    "stop",
    "cancel",
    "abort",
    "halt",
    "cici stop",
    "hey cici stop",
]


class InputProcessor:
    """
    Handles text input processing.

    Provides:
    - Text input processing (voice-to-CLI translation)
    - Stop word detection on complete words
    - Task cancellation on stop word detection

    Note: Audio processing is handled by the EARS service.
    This processor only handles text input.
    """

    def __init__(self):
        """Initialize the input processor."""
        self.stop_words = STOP_WORDS.copy()

    def detect_stop_word(self, text: str) -> bool:
        """
        Check if text contains a stop word.

        Only triggers on complete words/phrases to avoid false positives.

        Args:
            text: The text to check.

        Returns:
            True if a stop word was detected.
        """
        if not text:
            return False

        # strip punctuation from end for matching
        text_lower = text.lower().strip()
        text_stripped = text_lower.rstrip(".,!?")

        for stop_word in self.stop_words:
            # check for exact match (with or without trailing punctuation)
            if text_stripped == stop_word:
                return True
            if text_lower == stop_word:
                return True
            # check for stop word at end of sentence
            if text_stripped.endswith(f" {stop_word}"):
                return True

        return False

    async def process_text(self, text: str, session: "Session") -> dict:
        """
        Process text input.

        Applies voice-to-CLI translation and checks for stop words.

        Args:
            text: The text input.
            session: The session context.

        Returns:
            Dict with processing result:
            {
                "type": "text" | "stop",
                "original": str,
                "translated": str | None,
                "stop_detected": bool
            }
        """
        session.logger.info(f"processing text: {text}")
        session.update_activity()

        # check for stop word
        if self.detect_stop_word(text):
            session.logger.info(f"stop word detected: {text}")
            await session.cancel_active_tasks()
            return {
                "type": "stop",
                "original": text,
                "translated": None,
                "stop_detected": True
            }

        # check for triggers that should skip translation
        text_lower = text.lower().strip()
        # strip "hey cici" prefix for trigger check
        for prefix in ["hey cici", "hey sissy", "hey cc", "cici"]:
            if text_lower.startswith(prefix):
                text_lower = text_lower[len(prefix):].strip()
                if text_lower.startswith(","):
                    text_lower = text_lower[1:].strip()
                break

        # skip translation for "ask claude" - it's not a CLI command
        if text_lower.startswith("ask claude"):
            session.logger.info(f"skipping translation for ask claude trigger")
            return {
                "type": "text",
                "original": text,
                "translated": text,  # pass through unchanged
                "stop_detected": False
            }

        # translate voice-style text to CLI
        translated = parse_voice_to_cli(text)

        session.logger.info(f"translated: {text} -> {translated}")

        return {
            "type": "text",
            "original": text,
            "translated": translated,
            "stop_detected": False
        }

    def add_stop_word(self, word: str) -> None:
        """Add a custom stop word."""
        if word.lower() not in [w.lower() for w in self.stop_words]:
            self.stop_words.append(word.lower())
            logger.info(f"added stop word: {word}")

    def remove_stop_word(self, word: str) -> bool:
        """Remove a stop word."""
        word_lower = word.lower()
        for i, w in enumerate(self.stop_words):
            if w.lower() == word_lower:
                self.stop_words.pop(i)
                logger.info(f"removed stop word: {word}")
                return True
        return False
