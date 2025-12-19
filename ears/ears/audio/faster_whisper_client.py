# standard library imports
import tempfile
from typing import Optional

# 3rd-party imports
from loguru import logger
from faster_whisper import WhisperModel

# ------------------------------------------------------------------------------
# faster-whisper transcription client
# ------------------------------------------------------------------------------

_model: Optional[WhisperModel] = None


def load_model(
    model_size: str = "small",
    device: str = "cpu",
    compute_type: str = "int8"
) -> WhisperModel:
    """
    Load faster-whisper model, caching for reuse.

    :param model_size: Whisper model size (tiny, base, small, medium, large-v3)
    :param device: device to load model on (cpu or cuda)
    :param compute_type: quantization type (int8 for CPU, float16 for GPU)
    :return: loaded WhisperModel
    """
    global _model
    if _model is None:
        logger.info(f"loading faster-whisper model: {model_size} on {device} ({compute_type})")
        _model = WhisperModel(model_size, device=device, compute_type=compute_type)
        logger.info("faster-whisper model loaded successfully")
    return _model


def transcribe_audio(
    audio_bytes: bytes,
    model_size: str = "small",
    language: str = "en"
) -> Optional[str]:
    """
    Transcribe audio bytes to text using faster-whisper.

    :param audio_bytes: raw audio data in bytes (WAV, MP3, WebM, etc.)
    :param model_size: Whisper model size to use
    :param language: language code for transcription
    :return: transcribed text or None if transcription fails
    """
    if not audio_bytes:
        logger.warning("no audio data provided for transcription")
        return None

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
                beam_size=5,
                vad_filter=True,
                vad_parameters=dict(
                    min_silence_duration_ms=500,  # wait 500ms of silence before cutting
                    speech_pad_ms=200,  # pad speech with 200ms on each side
                ),
            )

            # segments is a generator - iterate to get all text
            text_parts = []
            for segment in segments:
                text_parts.append(segment.text.strip())

            text = " ".join(text_parts).strip()

            # filter common Whisper hallucinations
            hallucination_phrases = [
                "thank you",
                "thanks for watching",
                "subscribe",
                "see you next time",
                "bye",
                "goodbye",
                "thank you for watching",
                "thanks for listening",
            ]
            text_lower = text.lower()
            for phrase in hallucination_phrases:
                if text_lower == phrase or text_lower == phrase + ".":
                    logger.warning(f"filtered hallucination: {text}")
                    return None

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
