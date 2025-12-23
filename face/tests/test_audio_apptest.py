"""Test FACE audio components using Streamlit's AppTest framework.

These tests focus on what can be tested without real WebRTC/WebSocket connections:
- Configuration classes and their defaults
- Component imports and basic structure
- Unit tests for audio processing utilities

Note: streamlit-webrtc components require a browser and cannot be fully tested
with AppTest. Full E2E testing is done in test_audio_chat.py using Playwright.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add face directory to path for imports
FACE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(FACE_DIR))


# ------------------------------------------------------------------------------
# AudioStreamerConfig Tests
# ------------------------------------------------------------------------------

class TestAudioStreamerConfig:
    """Test the AudioStreamerConfig dataclass."""

    def test_default_websocket_url(self):
        """Verify default WebSocket URL is base localhost:8766 without debug."""
        from utils.audio_streamer import AudioStreamerConfig

        config = AudioStreamerConfig()
        assert config.websocket_url == "ws://localhost:8766"

    def test_default_chunk_duration(self):
        """Verify default chunk duration is 100ms."""
        from utils.audio_streamer import AudioStreamerConfig

        config = AudioStreamerConfig()
        assert config.chunk_duration_ms == 100

    def test_custom_websocket_url(self):
        """Verify custom WebSocket URL can be set."""
        from utils.audio_streamer import AudioStreamerConfig

        config = AudioStreamerConfig(websocket_url="ws://custom:9000")
        assert config.websocket_url == "ws://custom:9000"

    def test_custom_websocket_url_with_debug(self):
        """Verify WebSocket URL can include debug query parameter."""
        from utils.audio_streamer import AudioStreamerConfig

        config = AudioStreamerConfig(websocket_url="ws://localhost:8766?debug=true")
        assert config.websocket_url == "ws://localhost:8766?debug=true"
        assert "debug=true" in config.websocket_url

    def test_custom_chunk_duration(self):
        """Verify custom chunk duration can be set."""
        from utils.audio_streamer import AudioStreamerConfig

        config = AudioStreamerConfig(chunk_duration_ms=200)
        assert config.chunk_duration_ms == 200


# ------------------------------------------------------------------------------
# AudioProcessor Unit Tests
# ------------------------------------------------------------------------------

class TestAudioProcessorUnit:
    """Unit tests for AudioProcessor class (without real WebSocket)."""

    def test_initialization(self):
        """Verify AudioProcessor initializes with correct defaults."""
        from utils.audio_streamer import AudioProcessor

        processor = AudioProcessor("ws://localhost:8766")
        assert processor.websocket_url == "ws://localhost:8766"
        assert processor.ws is None
        assert processor.running is False
        assert processor.chunks_sent == 0
        assert processor.bytes_sent == 0

    def test_initialization_with_debug_url(self):
        """Verify AudioProcessor accepts debug mode URL."""
        from utils.audio_streamer import AudioProcessor

        processor = AudioProcessor("ws://localhost:8766?debug=true")
        assert "debug=true" in processor.websocket_url

    def test_send_audio_queues_data(self):
        """Verify send_audio adds data to queue."""
        from utils.audio_streamer import AudioProcessor

        processor = AudioProcessor("ws://localhost:8766")
        test_data = b"\x00" * 3200  # 100ms of silence

        processor.send_audio(test_data)

        # Data should be in the queue
        assert not processor.audio_queue.empty()
        queued_data = processor.audio_queue.get()
        assert queued_data == test_data

    def test_get_messages_returns_empty_initially(self):
        """Verify get_messages returns empty list initially."""
        from utils.audio_streamer import AudioProcessor

        processor = AudioProcessor("ws://localhost:8766")
        messages = processor.get_messages()
        assert messages == []


# ------------------------------------------------------------------------------
# Audio Format Constants Tests
# ------------------------------------------------------------------------------

class TestAudioFormatConstants:
    """Test audio format constants match EARS requirements."""

    def test_target_sample_rate(self):
        """Verify target sample rate is 16kHz (EARS requirement)."""
        from utils.audio_streamer import TARGET_SAMPLE_RATE

        assert TARGET_SAMPLE_RATE == 16000

    def test_target_channels(self):
        """Verify target channels is mono (EARS requirement)."""
        from utils.audio_streamer import TARGET_CHANNELS

        assert TARGET_CHANNELS == 1


# ------------------------------------------------------------------------------
# Chat Page Configuration Tests
# ------------------------------------------------------------------------------

class TestChatPageConfig:
    """Test chat page configuration values."""

    def test_ears_ws_url_constant(self):
        """Verify EARS WebSocket URL uses config (not hardcoded)."""
        # Can't fully import due to Streamlit dependencies, but we can check the file
        chat_file = FACE_DIR / "pages" / "chat.py"
        content = chat_file.read_text()

        # Should use config.ears_ws_url, not a hardcoded string
        assert "EARS_WS_URL = config.ears_ws_url" in content
        assert "TARGET_SAMPLE_RATE = config.sample_rate" in content

    def test_chat_page_imports_audio_processor(self):
        """Verify chat page has audio processor functionality."""
        chat_file = FACE_DIR / "pages" / "chat.py"
        content = chat_file.read_text()

        # Check for audio processing imports/code
        assert "AudioProcessor" in content or "audio_processor" in content
        assert "webrtc_streamer" in content


# ------------------------------------------------------------------------------
# Import Tests
# ------------------------------------------------------------------------------

class TestImports:
    """Test that all required modules can be imported."""

    def test_import_audio_streamer(self):
        """Verify audio_streamer module can be imported."""
        from utils import audio_streamer

        assert hasattr(audio_streamer, "AudioStreamerConfig")
        assert hasattr(audio_streamer, "AudioProcessor")
        assert hasattr(audio_streamer, "TARGET_SAMPLE_RATE")

    def test_import_audio_recorder(self):
        """Verify audio_recorder module can be imported."""
        from utils import audio_recorder

        assert hasattr(audio_recorder, "render_audio_recorder")

    def test_import_mind_client(self):
        """Verify mind_client module can be imported."""
        import mind_client

        assert hasattr(mind_client, "MindClient")
        assert hasattr(mind_client, "ConnectionState")
