"""Pydantic message schemas for EARS transcription service."""

from typing import Literal, Optional
from pydantic import BaseModel


# ------------------------------------------------------------------------------
# debug/diagnostic messages
# ------------------------------------------------------------------------------

class AudioDefect(BaseModel):
    """Individual audio defect detected during debug analysis."""
    code: str              # e.g., "low_volume", "silence", "clipping", "dc_offset"
    severity: str          # "warning" | "error"
    message: str           # Human-readable description
    value: float | None = None       # Measured value (e.g., RMS level, offset)
    threshold: float | None = None   # Threshold that was exceeded


class DebugMessage(BaseModel):
    """Sent when debug mode is enabled with audio analysis results."""
    type: Literal["debug"] = "debug"
    chunk_index: int       # Which chunk this analysis is for
    sample_count: int      # Number of samples in chunk
    duration_ms: float     # Chunk duration in milliseconds
    defects: list[AudioDefect]  # List of detected defects (empty if clean)
    metrics: dict          # Raw metrics: rms, peak, dc_offset, clipping_ratio, zcr


# ------------------------------------------------------------------------------
# server -> client messages
# ------------------------------------------------------------------------------

class ListeningMessage(BaseModel):
    """Sent when audio streaming starts."""
    type: Literal["listening"] = "listening"
    sample_rate: int = 16000


class TranscriptionMessage(BaseModel):
    """Sent when speech is transcribed."""
    type: Literal["transcription"] = "transcription"
    text: str
    final: bool  # True when speech segment is complete


class ErrorMessage(BaseModel):
    """Sent when an error occurs."""
    type: Literal["error"] = "error"
    message: str


class ClosedMessage(BaseModel):
    """Sent when server closes the connection."""
    type: Literal["closed"] = "closed"
    reason: str


# ------------------------------------------------------------------------------
# end of schemas.py
# ------------------------------------------------------------------------------
