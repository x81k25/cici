# standard library imports
import asyncio
import io
import wave
from dataclasses import dataclass, field
from typing import Callable, Optional
from collections import deque

# 3rd-party imports
from loguru import logger
from silero_vad import load_silero_vad, get_speech_timestamps
import torch

# local imports
from ears.audio.faster_whisper_client import transcribe_audio


# ------------------------------------------------------------------------------
# VAD configuration
# ------------------------------------------------------------------------------

@dataclass
class VADConfig:
    """Configuration for Voice Activity Detection."""
    # VAD thresholds
    speech_threshold: float = 0.5  # probability threshold for speech detection
    min_silence_duration_ms: int = 1000  # silence duration to end speech segment
    min_speech_duration_ms: int = 250  # minimum speech duration to process
    speech_pad_ms: int = 100  # padding around speech segments

    # Audio settings
    sample_rate: int = 16000  # required by silero-vad

    # Buffer settings
    max_buffer_seconds: float = 30.0  # max audio to buffer before force-flush


# ------------------------------------------------------------------------------
# streaming VAD processor
# ------------------------------------------------------------------------------

@dataclass
class VADProcessor:
    """
    Voice Activity Detection processor for streaming audio.

    Accumulates audio chunks, detects speech segments using Silero VAD,
    and triggers transcription when speech ends (silence detected).

    This is a pure transcription service - no command logic or triggers.
    """
    config: VADConfig = field(default_factory=VADConfig)

    # callbacks
    on_transcription: Optional[Callable[[str, bool], None]] = None  # (text, is_final)
    on_speech_start: Optional[Callable[[], None]] = None
    on_speech_end: Optional[Callable[[], None]] = None

    # internal state
    _model: torch.nn.Module = field(default=None, init=False, repr=False)
    _audio_buffer: deque = field(default_factory=deque, init=False, repr=False)
    _is_speaking: bool = field(default=False, init=False)
    _silence_frames: int = field(default=0, init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)

    def __post_init__(self):
        """Load VAD model after initialization."""
        self._load_model()

    def _load_model(self) -> None:
        """Load Silero VAD model."""
        if self._model is None:
            logger.info("loading Silero VAD model")
            self._model = load_silero_vad()
            logger.info("Silero VAD model loaded successfully")

    def reset(self) -> None:
        """Reset processor state."""
        self._audio_buffer.clear()
        self._is_speaking = False
        self._silence_frames = 0
        logger.debug("VAD processor reset")

    def _audio_bytes_to_tensor(self, audio_bytes: bytes) -> Optional[torch.Tensor]:
        """
        Convert raw audio bytes to torch tensor.

        Expects raw PCM Int16 audio at 16kHz mono (no WAV header).
        """
        try:
            # Int16 requires 2 bytes per sample - truncate trailing byte if odd length
            if len(audio_bytes) % 2 != 0:
                audio_bytes = audio_bytes[:-1]

            if len(audio_bytes) == 0:
                return None

            # raw PCM Int16 - convert directly to tensor (copy to avoid non-writable warning)
            audio_tensor = torch.frombuffer(bytearray(audio_bytes), dtype=torch.int16).float()
            # normalize to [-1, 1] range expected by silero-vad
            audio_tensor = audio_tensor / 32768.0

            # Debug: log audio stats to verify data is valid
            if len(audio_tensor) > 0:
                abs_max = audio_tensor.abs().max().item()
                abs_mean = audio_tensor.abs().mean().item()
                if abs_max > 0.01:  # Only log if there's actual signal
                    logger.debug(f"audio stats: samples={len(audio_tensor)}, abs_max={abs_max:.4f}, abs_mean={abs_mean:.4f}")

            return audio_tensor

        except Exception as e:
            logger.error(f"error converting audio to tensor: {e}")
            return None

    async def process_chunk(self, audio_bytes: bytes) -> Optional[dict]:
        """
        Process an audio chunk through VAD.

        Args:
            audio_bytes: Raw audio data (PCM Int16 expected)

        Returns:
            Dict with transcription results if speech ended, None otherwise
        """
        async with self._lock:
            # convert to tensor
            audio_tensor = self._audio_bytes_to_tensor(audio_bytes)
            if audio_tensor is None:
                return None

            # add to buffer
            self._audio_buffer.append(audio_tensor)

            # get total buffer duration
            total_samples = sum(t.shape[0] for t in self._audio_buffer)
            total_seconds = total_samples / self.config.sample_rate

            # run VAD on accumulated buffer (need enough audio for reliable detection)
            # minimum 0.5s of audio before running VAD
            if total_seconds < 0.5:
                chunk_duration_ms = len(audio_tensor) / self.config.sample_rate * 1000
                logger.debug(f"VAD chunk: {chunk_duration_ms:.0f}ms, buffering ({total_seconds:.2f}s)")
                return None

            # concatenate buffer for VAD analysis
            combined_audio = torch.cat(list(self._audio_buffer))

            # get speech timestamps on accumulated buffer
            speech_timestamps = get_speech_timestamps(
                combined_audio,
                self._model,
                threshold=self.config.speech_threshold,
                min_silence_duration_ms=self.config.min_silence_duration_ms,
                min_speech_duration_ms=self.config.min_speech_duration_ms,
                return_seconds=True,
            )

            has_speech = len(speech_timestamps) > 0
            chunk_duration_ms = len(audio_tensor) / self.config.sample_rate * 1000

            # check if speech ends before the end of buffer (silence at tail)
            speech_ends_early = False
            if has_speech:
                last_speech_end = speech_timestamps[-1]["end"]
                # if last speech ended more than min_silence_duration before buffer end, speech is done
                silence_at_end = total_seconds - last_speech_end
                if silence_at_end >= self.config.min_silence_duration_ms / 1000:
                    speech_ends_early = True
                    logger.debug(f"speech ended {silence_at_end:.2f}s ago")

            logger.debug(f"VAD chunk: {chunk_duration_ms:.0f}ms, buffer={total_seconds:.2f}s, has_speech={has_speech}, is_speaking={self._is_speaking}, ends_early={speech_ends_early}")

            # state machine: detect speech start/end
            if has_speech:
                if not self._is_speaking:
                    self._is_speaking = True
                    self._silence_frames = 0
                    logger.debug("speech started")
                    if self.on_speech_start:
                        self.on_speech_start()

                # check if speech has ended (silence detected at end of buffer)
                if speech_ends_early:
                    logger.debug("speech ended (silence detected)")
                    return await self._process_speech_end()
            else:
                # no speech detected in buffer
                if self._is_speaking:
                    # was speaking but no speech now - end of speech
                    logger.debug("speech ended (no speech in buffer)")
                    return await self._process_speech_end()
                elif total_seconds > 2.0:
                    # pure silence for 2+ seconds with no speech - clear buffer to prevent buildup
                    logger.debug(f"clearing silence buffer ({total_seconds:.1f}s)")
                    self._audio_buffer.clear()
                    return None

            # check buffer overflow
            if total_seconds > self.config.max_buffer_seconds:
                logger.warning(f"buffer overflow ({total_seconds:.1f}s), force processing")
                return await self._process_speech_end()

            return None

    async def _process_speech_end(self) -> Optional[dict]:
        """
        Process accumulated audio when speech ends.

        Transcribes the audio and returns the result.
        """
        if not self._audio_buffer:
            self._reset_speech_state()
            return None

        # callback
        if self.on_speech_end:
            self.on_speech_end()

        # concatenate all buffered audio
        combined_audio = torch.cat(list(self._audio_buffer))

        # trim to speech segments only (avoid sending silence to Whisper)
        trimmed_audio = self._trim_to_speech(combined_audio)
        if trimmed_audio is None or len(trimmed_audio) == 0:
            logger.debug("no speech segments found after trimming")
            self._reset_speech_state()
            return None

        # convert to bytes for transcription
        audio_bytes = self._tensor_to_wav_bytes(trimmed_audio)
        if audio_bytes is None:
            self._reset_speech_state()
            return None

        # transcribe
        logger.debug(f"transcribing {len(trimmed_audio) / self.config.sample_rate:.1f}s of audio (trimmed from {len(combined_audio) / self.config.sample_rate:.1f}s)")
        transcription = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: transcribe_audio(audio_bytes)
        )

        if not transcription:
            logger.debug("transcription returned empty/None")
            self._reset_speech_state()
            return None

        logger.info(f"transcription: {transcription}")

        # send transcription callback
        if self.on_transcription:
            self.on_transcription(transcription, True)

        # reset for next segment
        self._reset_speech_state()

        return {
            "type": "transcription",
            "text": transcription,
            "final": True,
        }

    def _reset_speech_state(self) -> None:
        """Reset speech detection state."""
        self._audio_buffer.clear()
        self._is_speaking = False
        self._silence_frames = 0

    def _trim_to_speech(self, audio: torch.Tensor) -> Optional[torch.Tensor]:
        """
        Trim audio to only include speech segments.

        Uses VAD to find speech boundaries and extracts only those portions,
        avoiding sending silence to Whisper (which causes hallucinations).
        """
        try:
            # get speech timestamps
            speech_timestamps = get_speech_timestamps(
                audio,
                self._model,
                threshold=self.config.speech_threshold,
                min_silence_duration_ms=self.config.min_silence_duration_ms,
                min_speech_duration_ms=self.config.min_speech_duration_ms,
                return_seconds=False,  # get sample indices
            )

            if not speech_timestamps:
                return None

            # calculate padding in samples
            pad_samples = int(self.config.speech_pad_ms * self.config.sample_rate / 1000)

            # extract speech segments with padding
            segments = []
            for ts in speech_timestamps:
                start = max(0, ts["start"] - pad_samples)
                end = min(len(audio), ts["end"] + pad_samples)
                segments.append(audio[start:end])

            if not segments:
                return None

            # concatenate all speech segments
            trimmed = torch.cat(segments)
            logger.debug(f"trimmed audio: {len(speech_timestamps)} segments, {len(trimmed) / self.config.sample_rate:.2f}s")

            return trimmed

        except Exception as e:
            logger.error(f"error trimming audio: {e}")
            return audio  # fall back to full audio

    def _tensor_to_wav_bytes(self, tensor: torch.Tensor) -> Optional[bytes]:
        """Convert torch tensor to WAV bytes."""
        try:
            # ensure 1D tensor
            if tensor.dim() > 1:
                tensor = tensor.squeeze()

            # convert from float [-1, 1] back to int16
            audio_int16 = (tensor * 32768.0).clamp(-32768, 32767).to(torch.int16)

            # write WAV using standard library
            buffer = io.BytesIO()
            with wave.open(buffer, "wb") as wav_file:
                wav_file.setnchannels(1)  # mono
                wav_file.setsampwidth(2)  # 16-bit = 2 bytes
                wav_file.setframerate(self.config.sample_rate)
                wav_file.writeframes(audio_int16.numpy().tobytes())

            buffer.seek(0)
            return buffer.read()
        except Exception as e:
            logger.error(f"error converting tensor to WAV: {e}")
            return None

    @property
    def is_speaking(self) -> bool:
        """Check if speech is currently detected."""
        return self._is_speaking

    @property
    def buffer_duration_seconds(self) -> float:
        """Get current buffer duration in seconds."""
        total_samples = sum(t.shape[0] for t in self._audio_buffer)
        return total_samples / self.config.sample_rate


# ------------------------------------------------------------------------------
# factory function
# ------------------------------------------------------------------------------

def create_vad_processor(
    min_silence_duration_ms: int = 600,
    on_transcription: Optional[Callable[[str, bool], None]] = None,
    on_speech_start: Optional[Callable[[], None]] = None,
    on_speech_end: Optional[Callable[[], None]] = None,
) -> VADProcessor:
    """
    Create a configured VAD processor.

    Args:
        min_silence_duration_ms: Silence duration to end speech segment
        on_transcription: Callback for transcriptions (text, is_final)
        on_speech_start: Callback when speech starts
        on_speech_end: Callback when speech ends

    Returns:
        Configured VADProcessor instance
    """
    config = VADConfig(
        min_silence_duration_ms=min_silence_duration_ms,
    )
    return VADProcessor(
        config=config,
        on_transcription=on_transcription,
        on_speech_start=on_speech_start,
        on_speech_end=on_speech_end,
    )


# ------------------------------------------------------------------------------
# end of vad_processor.py
# ------------------------------------------------------------------------------
