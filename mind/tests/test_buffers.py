# standard library imports
import asyncio

# 3rd-party imports
import pytest


# ------------------------------------------------------------------------------
# TranscriptBuffer tests
# ------------------------------------------------------------------------------

class TestTranscriptBuffer:
    """Tests for the TranscriptBuffer class."""

    @pytest.mark.asyncio
    async def test_buffer_starts_empty(self, transcript_buffer):
        """Test that buffer starts empty."""
        assert transcript_buffer.is_empty
        assert transcript_buffer.words == []

    @pytest.mark.asyncio
    async def test_add_word(self, transcript_buffer):
        """Test adding words to buffer."""
        result = await transcript_buffer.add_word("hello")

        assert result["status"] == "buffered"
        assert result["buffer"] == ["hello"]
        assert not transcript_buffer.is_empty

    @pytest.mark.asyncio
    async def test_add_multiple_words(self, transcript_buffer):
        """Test adding multiple words."""
        await transcript_buffer.add_word("hey")
        await transcript_buffer.add_word("cici")
        result = await transcript_buffer.add_word("list")

        assert result["buffer"] == ["hey", "cici", "list"]

    @pytest.mark.asyncio
    async def test_is_execute(self, transcript_buffer):
        """Test execute trigger detection."""
        assert transcript_buffer.is_execute("execute")
        assert transcript_buffer.is_execute("Execute")
        assert transcript_buffer.is_execute("EXECUTE")
        assert transcript_buffer.is_execute("  execute  ")

        assert not transcript_buffer.is_execute("hello")
        assert not transcript_buffer.is_execute("exec")

    @pytest.mark.asyncio
    async def test_get_and_clear(self, transcript_buffer):
        """Test getting full command and clearing buffer."""
        await transcript_buffer.add_word("hey")
        await transcript_buffer.add_word("cici")
        await transcript_buffer.add_word("list")
        await transcript_buffer.add_word("files")

        command = await transcript_buffer.get_and_clear()

        assert command == "hey cici list files"
        assert transcript_buffer.is_empty

    @pytest.mark.asyncio
    async def test_clear(self, transcript_buffer):
        """Test clearing buffer without returning contents."""
        await transcript_buffer.add_word("hello")
        await transcript_buffer.add_word("world")

        await transcript_buffer.clear()

        assert transcript_buffer.is_empty

    @pytest.mark.asyncio
    async def test_empty_get_and_clear(self, transcript_buffer):
        """Test get_and_clear on empty buffer."""
        command = await transcript_buffer.get_and_clear()
        assert command == ""

    @pytest.mark.asyncio
    async def test_strips_whitespace(self, transcript_buffer):
        """Test that words are stripped of whitespace."""
        await transcript_buffer.add_word("  hello  ")
        result = await transcript_buffer.add_word("  world  ")

        assert result["buffer"] == ["hello", "world"]

    @pytest.mark.asyncio
    async def test_empty_words_ignored(self, transcript_buffer):
        """Test that empty words are ignored."""
        await transcript_buffer.add_word("hello")
        await transcript_buffer.add_word("")
        await transcript_buffer.add_word("   ")
        result = await transcript_buffer.add_word("world")

        assert result["buffer"] == ["hello", "world"]


# ------------------------------------------------------------------------------
# MessageBuffer tests
# ------------------------------------------------------------------------------

class TestMessageBuffer:
    """Tests for the MessageBuffer class."""

    @pytest.mark.asyncio
    async def test_buffer_starts_empty(self, message_buffer):
        """Test that buffer starts empty."""
        assert message_buffer.is_empty
        assert message_buffer.count == 0

    @pytest.mark.asyncio
    async def test_add_message(self, message_buffer):
        """Test adding a message."""
        await message_buffer.add({"type": "test", "content": "hello"})

        assert message_buffer.count == 1
        assert not message_buffer.is_empty

    @pytest.mark.asyncio
    async def test_add_message_with_timestamp(self, message_buffer):
        """Test that timestamp is added automatically."""
        await message_buffer.add({"type": "test", "content": "hello"})

        messages = await message_buffer.peek()

        assert len(messages) == 1
        assert "timestamp" in messages[0]

    @pytest.mark.asyncio
    async def test_preserves_existing_timestamp(self, message_buffer):
        """Test that existing timestamp is preserved."""
        await message_buffer.add({
            "type": "test",
            "content": "hello",
            "timestamp": "2024-01-01T00:00:00"
        })

        messages = await message_buffer.peek()

        assert messages[0]["timestamp"] == "2024-01-01T00:00:00"

    @pytest.mark.asyncio
    async def test_get_and_clear(self, message_buffer):
        """Test getting all messages and clearing buffer."""
        await message_buffer.add({"type": "test", "content": "one"})
        await message_buffer.add({"type": "test", "content": "two"})

        messages = await message_buffer.get_and_clear()

        assert len(messages) == 2
        assert messages[0]["content"] == "one"
        assert messages[1]["content"] == "two"
        assert message_buffer.is_empty

    @pytest.mark.asyncio
    async def test_peek_does_not_clear(self, message_buffer):
        """Test that peek doesn't clear the buffer."""
        await message_buffer.add({"type": "test", "content": "hello"})

        messages1 = await message_buffer.peek()
        messages2 = await message_buffer.peek()

        assert len(messages1) == 1
        assert len(messages2) == 1
        assert message_buffer.count == 1

    @pytest.mark.asyncio
    async def test_clear(self, message_buffer):
        """Test clearing buffer."""
        await message_buffer.add({"type": "test", "content": "one"})
        await message_buffer.add({"type": "test", "content": "two"})

        count = await message_buffer.clear()

        assert count == 2
        assert message_buffer.is_empty

    @pytest.mark.asyncio
    async def test_clear_empty_buffer(self, message_buffer):
        """Test clearing empty buffer."""
        count = await message_buffer.clear()
        assert count == 0
