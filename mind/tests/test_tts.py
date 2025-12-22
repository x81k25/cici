# standard library imports
from unittest.mock import AsyncMock, patch, MagicMock

# 3rd-party imports
import pytest
import httpx


# ------------------------------------------------------------------------------
# SentenceBuffer tests
# ------------------------------------------------------------------------------

class TestSentenceBuffer:
    """Tests for the SentenceBuffer class."""

    def test_add_single_sentence(self):
        """Single complete sentence is extracted."""
        from mind.core.sentence_detector import SentenceBuffer
        buffer = SentenceBuffer()
        sentences = buffer.add("Hello world. ")
        assert sentences == ["Hello world."]

    def test_add_multiple_sentences(self):
        """Multiple complete sentences are extracted."""
        from mind.core.sentence_detector import SentenceBuffer
        buffer = SentenceBuffer()
        sentences = buffer.add("First sentence. Second sentence. ")
        assert sentences == ["First sentence.", "Second sentence."]

    def test_add_incomplete_sentence(self):
        """Incomplete sentence is buffered, not returned."""
        from mind.core.sentence_detector import SentenceBuffer
        buffer = SentenceBuffer()
        sentences = buffer.add("Hello world")
        assert sentences == []
        assert buffer.buffer == "Hello world"

    def test_add_across_chunks(self):
        """Sentence split across chunks is handled correctly."""
        from mind.core.sentence_detector import SentenceBuffer
        buffer = SentenceBuffer()

        sentences1 = buffer.add("Hello ")
        assert sentences1 == []

        sentences2 = buffer.add("world. ")
        assert sentences2 == ["Hello world."]

    def test_flush_remaining_content(self):
        """Flush returns remaining content."""
        from mind.core.sentence_detector import SentenceBuffer
        buffer = SentenceBuffer()
        buffer.add("Hello world")
        remaining = buffer.flush()
        assert remaining == "Hello world"
        assert buffer.buffer == ""

    def test_flush_empty_buffer(self):
        """Flush on empty buffer returns None."""
        from mind.core.sentence_detector import SentenceBuffer
        buffer = SentenceBuffer()
        remaining = buffer.flush()
        assert remaining is None

    def test_clear_buffer(self):
        """Clear removes content without returning it."""
        from mind.core.sentence_detector import SentenceBuffer
        buffer = SentenceBuffer()
        buffer.add("Hello world")
        buffer.clear()
        assert buffer.buffer == ""

    def test_exclamation_mark_ends_sentence(self):
        """Exclamation marks end sentences."""
        from mind.core.sentence_detector import SentenceBuffer
        buffer = SentenceBuffer()
        sentences = buffer.add("Hello! World! ")
        assert sentences == ["Hello!", "World!"]

    def test_question_mark_ends_sentence(self):
        """Question marks end sentences."""
        from mind.core.sentence_detector import SentenceBuffer
        buffer = SentenceBuffer()
        sentences = buffer.add("How are you? I'm fine. ")
        assert sentences == ["How are you?", "I'm fine."]


# ------------------------------------------------------------------------------
# TTS Client tests
# ------------------------------------------------------------------------------

class TestTTSClient:
    """Tests for the TTS client functions."""

    @pytest.mark.asyncio
    async def test_send_to_tts_success(self):
        """Successful TTS request returns True."""
        from mind.core.tts_client import send_to_tts

        mock_response = MagicMock()
        mock_response.status_code = 202

        with patch('mind.core.tts_client.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            result = await send_to_tts("Test sentence.")
            assert result is True

            mock_client.post.assert_called_once()
            call_args = mock_client.post.call_args
            assert "Test sentence." in str(call_args)

    @pytest.mark.asyncio
    async def test_send_to_tts_empty_string(self):
        """Empty string returns False without making request."""
        from mind.core.tts_client import send_to_tts

        with patch('mind.core.tts_client.httpx.AsyncClient') as mock_client_class:
            result = await send_to_tts("")
            assert result is False
            mock_client_class.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_to_tts_whitespace_only(self):
        """Whitespace-only string returns False."""
        from mind.core.tts_client import send_to_tts

        with patch('mind.core.tts_client.httpx.AsyncClient') as mock_client_class:
            result = await send_to_tts("   ")
            assert result is False
            mock_client_class.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_to_tts_service_unavailable(self):
        """Service unavailable returns False without blocking."""
        from mind.core.tts_client import send_to_tts

        with patch('mind.core.tts_client.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post.side_effect = httpx.RequestError("Connection refused")
            mock_client_class.return_value.__aenter__.return_value = mock_client

            result = await send_to_tts("Test sentence.")
            assert result is False

    @pytest.mark.asyncio
    async def test_send_to_tts_rejected(self):
        """Non-202 status code returns False."""
        from mind.core.tts_client import send_to_tts

        mock_response = MagicMock()
        mock_response.status_code = 500

        with patch('mind.core.tts_client.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            result = await send_to_tts("Test sentence.")
            assert result is False

    @pytest.mark.asyncio
    async def test_send_to_tts_with_request_id(self):
        """Request ID is passed to TTS service."""
        from mind.core.tts_client import send_to_tts

        mock_response = MagicMock()
        mock_response.status_code = 202

        with patch('mind.core.tts_client.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            result = await send_to_tts("Test.", request_id="test-123")
            assert result is True

            call_args = mock_client.post.call_args
            json_arg = call_args.kwargs.get('json') or call_args[1].get('json')
            assert json_arg['request_id'] == "test-123"

    @pytest.mark.asyncio
    async def test_check_tts_health_success(self):
        """Health check returns True when service is healthy."""
        from mind.core.tts_client import check_tts_health

        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch('mind.core.tts_client.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            result = await check_tts_health()
            assert result is True

    @pytest.mark.asyncio
    async def test_check_tts_health_failure(self):
        """Health check returns False when service is unavailable."""
        from mind.core.tts_client import check_tts_health

        with patch('mind.core.tts_client.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get.side_effect = httpx.RequestError("Connection refused")
            mock_client_class.return_value.__aenter__.return_value = mock_client

            result = await check_tts_health()
            assert result is False
