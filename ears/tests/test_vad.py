# 3rd-party imports
import pytest


# ------------------------------------------------------------------------------
# VAD processor tests
# ------------------------------------------------------------------------------

class TestVADProcessor:
    """Tests for Voice Activity Detection processor."""

    def test_vad_processor_initialization(self):
        """Test that VAD processor initializes correctly."""
        from ears.audio.vad_processor import create_vad_processor

        processor = create_vad_processor()

        assert processor is not None
        assert processor._model is not None
        assert processor.is_speaking is False

    def test_vad_processor_reset(self):
        """Test that reset clears state."""
        from ears.audio.vad_processor import create_vad_processor

        processor = create_vad_processor()
        processor._is_speaking = True
        processor._silence_frames = 5

        processor.reset()

        assert processor.is_speaking is False
        assert processor._silence_frames == 0

    def test_vad_config_defaults(self):
        """Test VAD config has sensible defaults."""
        from ears.audio.vad_processor import VADConfig

        config = VADConfig()

        assert config.sample_rate == 16000
        assert config.min_silence_duration_ms == 600
        assert config.max_buffer_seconds == 30.0
        assert config.speech_threshold == 0.5

    def test_vad_config_no_execute_trigger(self):
        """Test that VADConfig no longer has execute_trigger."""
        from ears.audio.vad_processor import VADConfig

        config = VADConfig()

        # execute_trigger should NOT exist in simplified EARS VAD
        assert not hasattr(config, 'execute_trigger')

    def test_vad_processor_buffer_duration(self):
        """Test buffer duration calculation."""
        from ears.audio.vad_processor import create_vad_processor

        processor = create_vad_processor()

        # empty buffer
        assert processor.buffer_duration_seconds == 0.0

    def test_vad_processor_callbacks(self):
        """Test that callbacks are stored correctly."""
        from ears.audio.vad_processor import create_vad_processor

        on_transcription_called = []
        on_speech_start_called = []

        def on_transcription(text, is_final):
            on_transcription_called.append((text, is_final))

        def on_speech_start():
            on_speech_start_called.append(True)

        processor = create_vad_processor(
            on_transcription=on_transcription,
            on_speech_start=on_speech_start,
        )

        assert processor.on_transcription is not None
        assert processor.on_speech_start is not None


class TestVADConfig:
    """Tests for VADConfig dataclass."""

    def test_config_custom_values(self):
        """Test VADConfig with custom values."""
        from ears.audio.vad_processor import VADConfig

        config = VADConfig(
            speech_threshold=0.7,
            min_silence_duration_ms=1000,
            max_buffer_seconds=60.0,
        )

        assert config.speech_threshold == 0.7
        assert config.min_silence_duration_ms == 1000
        assert config.max_buffer_seconds == 60.0

    def test_config_sample_rate_immutable(self):
        """Test that sample rate defaults to 16kHz (required by silero)."""
        from ears.audio.vad_processor import VADConfig

        config = VADConfig()
        assert config.sample_rate == 16000
