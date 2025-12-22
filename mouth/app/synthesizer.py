"""Piper TTS synthesizer wrapper with background processing."""

import io
import logging
import threading
import wave
from typing import Optional

from piper import PiperVoice

from app.config import settings
from app.queue_manager import queue_manager, AudioChunk

logger = logging.getLogger(__name__)


class Synthesizer:
    """
    Wrapper for Piper TTS that runs in a background thread.

    Pulls text from the pending queue, synthesizes with Piper,
    and pushes completed audio to the completed buffer.
    """

    def __init__(self):
        self._voice: Optional[PiperVoice] = None
        self._worker_thread: Optional[threading.Thread] = None
        self._shutdown_event = threading.Event()
        self._running = False

    def _load_voice(self) -> None:
        """Load the Piper voice model."""
        logger.info(
            f"Loading Piper model from {settings.piper_model_path}"
        )
        self._voice = PiperVoice.load(
            str(settings.piper_model_path),
            config_path=str(settings.piper_config_path),
        )
        logger.info("Piper model loaded successfully")

    def _synthesize_to_wav(self, text: str) -> bytes:
        """Synthesize text to WAV audio bytes."""
        if self._voice is None:
            raise RuntimeError("Voice model not loaded")

        # Synthesize to WAV in memory
        audio_buffer = io.BytesIO()

        with wave.open(audio_buffer, "wb") as wav_file:
            self._voice.synthesize_wav(text, wav_file)

        return audio_buffer.getvalue()

    def _worker_loop(self) -> None:
        """Background worker that processes the pending queue."""
        logger.info("Synthesizer worker thread started")

        while not self._shutdown_event.is_set():
            # Wait for an item with a timeout so we can check shutdown
            item = queue_manager.pop_pending(timeout=0.5)

            if item is None:
                continue

            try:
                logger.debug(f"Synthesizing: {item.text[:50]}...")
                audio_data = self._synthesize_to_wav(item.text)

                chunk = AudioChunk(
                    audio_data=audio_data,
                    text=item.text,
                    request_id=item.request_id,
                )
                queue_manager.push_completed(chunk)
                logger.debug(f"Completed synthesis for request {item.request_id}")

            except Exception as e:
                logger.error(f"Synthesis failed for '{item.text[:30]}...': {e}")

        logger.info("Synthesizer worker thread stopped")

    def start(self) -> None:
        """Start the synthesizer background worker."""
        if self._running:
            logger.warning("Synthesizer already running")
            return

        self._load_voice()
        self._shutdown_event.clear()
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            name="tts-synthesizer",
            daemon=True,
        )
        self._worker_thread.start()
        self._running = True
        logger.info("Synthesizer started")

    def stop(self, timeout: float = 5.0) -> None:
        """Stop the synthesizer background worker."""
        if not self._running:
            return

        logger.info("Stopping synthesizer...")
        self._shutdown_event.set()

        if self._worker_thread is not None:
            self._worker_thread.join(timeout=timeout)
            if self._worker_thread.is_alive():
                logger.warning("Synthesizer thread did not stop gracefully")

        self._running = False
        self._voice = None
        logger.info("Synthesizer stopped")

    @property
    def is_running(self) -> bool:
        """Check if synthesizer is running."""
        return self._running


# Global synthesizer instance
synthesizer = Synthesizer()
