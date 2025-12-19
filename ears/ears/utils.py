# standard library imports
import io
from typing import Optional

# 3rd-party imports
from loguru import logger
import numpy as np
import pydub


# ------------------------------------------------------------------------------
# audio utility functions
# ------------------------------------------------------------------------------


def wav_bytes_to_whisper_format(wav_bytes: bytes) -> Optional[bytes]:
    """
    Convert WAV bytes to Whisper-compatible format (16kHz mono).

    Args:
        wav_bytes: Input WAV audio bytes.

    Returns:
        Resampled WAV bytes suitable for Whisper, or None if conversion fails.
    """
    if not wav_bytes:
        return None

    try:
        # load audio from bytes
        audio_segment = pydub.AudioSegment.from_wav(io.BytesIO(wav_bytes))

        # convert to mono if stereo
        if audio_segment.channels > 1:
            audio_segment = audio_segment.set_channels(1)

        # check if audio is too quiet (likely silence)
        current_dbfs = audio_segment.dBFS
        if current_dbfs < -40:
            logger.debug(f"skipping silent audio: {current_dbfs:.1f} dBFS")
            return None

        # normalize audio to improve transcription quality
        target_dbfs = -20.0
        gain_needed = target_dbfs - current_dbfs
        gain_needed = min(gain_needed, 20.0)
        if gain_needed > 0:
            audio_segment = audio_segment.apply_gain(gain_needed)
            logger.debug(f"normalized: {current_dbfs:.1f} -> {audio_segment.dBFS:.1f} dBFS")

        # resample to 16kHz for Whisper
        audio_segment = audio_segment.set_frame_rate(16000)

        # export to WAV bytes
        buffer = io.BytesIO()
        audio_segment.export(buffer, format="wav")
        return buffer.getvalue()

    except Exception as e:
        logger.error(f"error processing audio: {e}")
        return None


def raw_audio_to_wav(
    audio_data: bytes,
    sample_rate: int = 16000,
    sample_width: int = 2,
    channels: int = 1
) -> bytes:
    """
    Convert raw PCM audio data to WAV format.

    Args:
        audio_data: Raw PCM audio bytes.
        sample_rate: Sample rate in Hz.
        sample_width: Bytes per sample (1=8-bit, 2=16-bit).
        channels: Number of audio channels.

    Returns:
        WAV file bytes.
    """
    audio_segment = pydub.AudioSegment(
        audio_data,
        frame_rate=sample_rate,
        sample_width=sample_width,
        channels=channels
    )

    buffer = io.BytesIO()
    audio_segment.export(buffer, format="wav")
    return buffer.getvalue()
