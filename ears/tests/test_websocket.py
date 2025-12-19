# standard library imports
from unittest.mock import AsyncMock, MagicMock, patch

# 3rd-party imports
import pytest


# ------------------------------------------------------------------------------
# WebSocket server tests
# ------------------------------------------------------------------------------

class TestSchemas:
    """Tests for EARS message schemas."""

    def test_listening_message(self):
        """Test ListeningMessage schema."""
        from ears.schemas import ListeningMessage

        msg = ListeningMessage()

        assert msg.type == "listening"
        assert msg.sample_rate == 16000

    def test_transcription_message(self):
        """Test TranscriptionMessage schema."""
        from ears.schemas import TranscriptionMessage

        msg = TranscriptionMessage(text="hello world", final=True)

        assert msg.type == "transcription"
        assert msg.text == "hello world"
        assert msg.final is True

    def test_transcription_message_partial(self):
        """Test TranscriptionMessage for partial transcription."""
        from ears.schemas import TranscriptionMessage

        msg = TranscriptionMessage(text="partial text", final=False)

        assert msg.final is False

    def test_error_message(self):
        """Test ErrorMessage schema."""
        from ears.schemas import ErrorMessage

        msg = ErrorMessage(message="something went wrong")

        assert msg.type == "error"
        assert msg.message == "something went wrong"

    def test_closed_message(self):
        """Test ClosedMessage schema."""
        from ears.schemas import ClosedMessage

        msg = ClosedMessage(reason="client disconnected")

        assert msg.type == "closed"
        assert msg.reason == "client disconnected"


class TestWebSocketHandler:
    """Tests for WebSocket audio handler."""

    @pytest.mark.asyncio
    async def test_handler_ignores_non_binary_messages(self, mock_websocket):
        """Test that handler ignores non-binary messages."""
        from ears.main import handle_audio_stream

        # Create an async iterator for the websocket
        async def mock_iter():
            yield "text message"

        mock_websocket.__aiter__ = lambda self: mock_iter()

        with patch("ears.main.create_vad_processor") as mock_vad:
            mock_processor = MagicMock()
            mock_processor.reset = MagicMock()
            mock_vad.return_value = mock_processor

            await handle_audio_stream(mock_websocket)

            # Should not have called process_chunk with text
            mock_processor.process_chunk.assert_not_called()

    @pytest.mark.asyncio
    async def test_handler_sends_listening_on_first_chunk(self, mock_websocket):
        """Test that handler sends listening message on first audio chunk."""
        import json
        from ears.main import handle_audio_stream

        # Mock audio chunk
        audio_chunk = b"\x00\x01" * 1000

        # Create an async iterator for the websocket
        async def mock_iter():
            yield audio_chunk

        mock_websocket.__aiter__ = lambda self: mock_iter()

        with patch("ears.main.create_vad_processor") as mock_vad:
            mock_processor = MagicMock()
            mock_processor.reset = MagicMock()
            mock_processor.process_chunk = AsyncMock(return_value=None)
            mock_vad.return_value = mock_processor

            await handle_audio_stream(mock_websocket)

            # Should have sent listening message
            mock_websocket.send.assert_called()
            sent_data = mock_websocket.send.call_args[0][0]
            msg = json.loads(sent_data)
            assert msg["type"] == "listening"

    @pytest.mark.asyncio
    async def test_handler_sends_transcription_on_speech_end(self, mock_websocket):
        """Test that handler sends transcription when speech ends."""
        import json
        from ears.main import handle_audio_stream

        # Mock audio chunks
        audio_chunks = [b"\x00\x01" * 1000, b"\x00\x02" * 1000]

        # Create an async iterator for the websocket
        async def mock_iter():
            for chunk in audio_chunks:
                yield chunk

        mock_websocket.__aiter__ = lambda self: mock_iter()

        with patch("ears.main.create_vad_processor") as mock_vad:
            mock_processor = MagicMock()
            mock_processor.reset = MagicMock()

            # First chunk: no transcription, second chunk: transcription ready
            mock_processor.process_chunk = AsyncMock(
                side_effect=[
                    None,  # first chunk
                    {"type": "transcription", "text": "hello world", "final": True},  # second chunk
                ]
            )
            mock_vad.return_value = mock_processor

            await handle_audio_stream(mock_websocket)

            # Should have sent listening + transcription
            assert mock_websocket.send.call_count >= 2

            # Check last call was transcription
            calls = [json.loads(call[0][0]) for call in mock_websocket.send.call_args_list]
            transcription_calls = [c for c in calls if c.get("type") == "transcription"]
            assert len(transcription_calls) == 1
            assert transcription_calls[0]["text"] == "hello world"


class TestServerMain:
    """Tests for server main module."""

    def test_run_server_function_exists(self):
        """Test that run_server function is available."""
        from ears.main import run_server

        assert callable(run_server)

    def test_main_function_exists(self):
        """Test that main async function is available."""
        from ears.main import main

        assert callable(main)

    def test_default_port(self):
        """Test that EARS uses port 8766 by default (different from main cici)."""
        import inspect
        from ears.main import run_server

        sig = inspect.signature(run_server)
        port_default = sig.parameters["port"].default

        assert port_default == 8766
