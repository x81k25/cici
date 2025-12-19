"""Pydantic message schemas for EARS transcription service."""

from typing import Literal, Optional
from pydantic import BaseModel


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
