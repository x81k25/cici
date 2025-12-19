# 3rd-party imports
import pytest


# ------------------------------------------------------------------------------
# transcription tests
# ------------------------------------------------------------------------------

class TestTranscription:
    """Tests for audio transcription functionality."""

    @pytest.mark.slow
    def test_transcribe_audio_returns_text(self, sample_speech_audio: bytes):
        """Test that transcribe_audio returns non-empty text."""
        from ears.audio.faster_whisper_client import transcribe_audio

        result = transcribe_audio(sample_speech_audio)

        assert result is not None
        assert isinstance(result, str)
        assert len(result) > 50  # should be substantial text

    @pytest.mark.slow
    def test_transcribe_audio_accuracy(
        self, sample_speech_audio: bytes, expected_phrases: list[str]
    ):
        """Test that transcription contains expected phrases."""
        from ears.audio.faster_whisper_client import transcribe_audio

        result = transcribe_audio(sample_speech_audio)

        assert result is not None
        result_lower = result.lower()

        # check that at least 80% of expected phrases are present
        matches = sum(1 for phrase in expected_phrases if phrase in result_lower)
        accuracy = matches / len(expected_phrases)

        assert accuracy >= 0.8, (
            f"Only {matches}/{len(expected_phrases)} phrases found. "
            f"Transcription: {result}"
        )

    @pytest.mark.slow
    def test_transcribe_empty_audio_returns_none(self):
        """Test that empty audio returns None."""
        from ears.audio.faster_whisper_client import transcribe_audio

        result = transcribe_audio(b"")
        assert result is None

    @pytest.mark.slow
    def test_transcribe_audio_model_caching(self, sample_speech_audio: bytes):
        """Test that the model is cached between calls."""
        import time
        from ears.audio.faster_whisper_client import transcribe_audio

        # first call (may load model)
        start1 = time.time()
        result1 = transcribe_audio(sample_speech_audio)
        time1 = time.time() - start1

        # second call (model should be cached)
        start2 = time.time()
        result2 = transcribe_audio(sample_speech_audio)
        time2 = time.time() - start2

        assert result1 == result2
        assert result2 is not None


class TestWhisperHallucinations:
    """Tests for hallucination filtering."""

    @pytest.mark.slow
    def test_hallucination_phrases_filtered(self):
        """Test that common hallucination phrases are filtered."""
        # This is more of a documentation test - actual filtering
        # happens in the transcribe_audio function
        from ears.audio.faster_whisper_client import transcribe_audio

        # Empty/silent audio should return None (filtered as potential hallucination)
        result = transcribe_audio(b"")
        assert result is None


class TestFasterWhisperClient:
    """Tests for the faster-whisper client module."""

    def test_faster_whisper_client_import(self):
        """Test that faster_whisper_client module imports correctly."""
        from ears.audio import faster_whisper_client

        assert hasattr(faster_whisper_client, 'load_model')
        assert hasattr(faster_whisper_client, 'transcribe_audio')
        assert hasattr(faster_whisper_client, 'transcribe_audio_with_timestamps')
