# standard library imports
import tempfile
from typing import Optional

# 3rd-party imports
from loguru import logger
from faster_whisper import WhisperModel

# local imports
from ears.config import config
from ears.normalize import normalize_transcription

# ------------------------------------------------------------------------------
# faster-whisper transcription client
# ------------------------------------------------------------------------------

_model: Optional[WhisperModel] = None


def load_model(
    model_size: str = None,
    device: str = None,
    compute_type: str = None
) -> WhisperModel:
    """
    Load faster-whisper model, caching for reuse.

    :param model_size: Whisper model size (defaults to config)
    :param device: device to load model on (defaults to config)
    :param compute_type: quantization type (defaults to config)
    :return: loaded WhisperModel
    """
    global _model

    # Use config defaults
    model_size = model_size or config.whisper.model_size
    device = device or config.whisper.device
    compute_type = compute_type or config.whisper.compute_type

    if _model is None:
        logger.info(f"loading faster-whisper model: {model_size} on {device} ({compute_type})")
        _model = WhisperModel(model_size, device=device, compute_type=compute_type)
        logger.info("faster-whisper model loaded successfully")
    return _model


def transcribe_audio(
    audio_bytes: bytes,
    model_size: str = None,
    language: str = None
) -> Optional[str]:
    """
    Transcribe audio bytes to text using faster-whisper.

    :param audio_bytes: raw audio data in bytes (WAV, MP3, WebM, etc.)
    :param model_size: Whisper model size to use (defaults to config)
    :param language: language code for transcription (defaults to config)
    :return: transcribed text or None if transcription fails
    """
    if not audio_bytes:
        logger.warning("no audio data provided for transcription")
        return None

    # Use config defaults
    language = language or config.whisper.language

    try:
        model = load_model(model_size)

        # write audio bytes to temporary file for faster-whisper
        # faster-whisper handles format conversion internally via PyAV
        with tempfile.NamedTemporaryFile(suffix=".audio", delete=True) as tmp_file:
            tmp_file.write(audio_bytes)
            tmp_file.flush()

            logger.debug(f"transcribing audio file: {tmp_file.name}")

            # transcribe with VAD filter enabled for better accuracy
            segments, info = model.transcribe(
                tmp_file.name,
                language=language,
                beam_size=config.whisper.beam_size,
                vad_filter=True,
                vad_parameters=dict(
                    min_silence_duration_ms=config.whisper.vad_min_silence_duration_ms,
                    speech_pad_ms=config.whisper.vad_speech_pad_ms,
                ),
            )

            # segments is a generator - iterate to get all text
            text_parts = []
            for segment in segments:
                text_parts.append(segment.text.strip())

            text = " ".join(text_parts).strip()

            # filter common Whisper hallucinations
            text_lower = text.lower()
            for phrase in config.hallucination_phrases:
                if text_lower == phrase or text_lower == phrase + ".":
                    logger.warning(f"filtered hallucination: {text}")
                    return None

            # apply word alias normalization (e.g., "CeCe" -> "cici")
            text = normalize_transcription(text)

            logger.info(f"transcription result: {text}")
            return text if text else None

    except Exception as e:
        logger.error(f"transcription error: {e}")
        return None


def transcribe_audio_with_timestamps(
    audio_bytes: bytes,
    model_size: str = "small",
    language: str = "en"
) -> Optional[list[dict]]:
    """
    Transcribe audio bytes to text with word-level timestamps.

    :param audio_bytes: raw audio data in bytes
    :param model_size: Whisper model size to use
    :param language: language code for transcription
    :return: list of segments with timestamps, or None if transcription fails
    """
    if not audio_bytes:
        logger.warning("no audio data provided for transcription")
        return None

    try:
        model = load_model(model_size)

        with tempfile.NamedTemporaryFile(suffix=".audio", delete=True) as tmp_file:
            tmp_file.write(audio_bytes)
            tmp_file.flush()

            segments, info = model.transcribe(
                tmp_file.name,
                language=language,
                beam_size=5,
                word_timestamps=True,
                vad_filter=True,
            )

            result = []
            for segment in segments:
                segment_data = {
                    "start": segment.start,
                    "end": segment.end,
                    "text": segment.text.strip(),
                    "words": []
                }
                if segment.words:
                    for word in segment.words:
                        segment_data["words"].append({
                            "word": word.word,
                            "start": word.start,
                            "end": word.end,
                            "probability": word.probability
                        })
                result.append(segment_data)

            return result if result else None

    except Exception as e:
        logger.error(f"transcription error: {e}")
        return None


# ------------------------------------------------------------------------------
# end of faster_whisper_client.py
# ------------------------------------------------------------------------------
