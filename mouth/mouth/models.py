"""Pydantic models for TTS service request/response schemas."""

from pydantic import BaseModel, Field
from typing import Optional


class SynthesizeRequest(BaseModel):
    """Request body for POST /synthesize endpoint."""

    text: str = Field(..., min_length=1, description="Sentence to synthesize")
    request_id: Optional[str] = Field(None, description="For tracing/logging")


class SynthesizeResponse(BaseModel):
    """Response for POST /synthesize endpoint."""

    status: str = Field("queued", description="Status of the request")
    request_id: Optional[str] = Field(None, description="Echo back request ID")
    queue_position: int = Field(..., description="Position in the pending queue")
    pending_count: int = Field(..., description="Total items in pending queue")


class QueueStatus(BaseModel):
    """Queue status information."""

    pending_count: int = Field(..., description="Number of sentences awaiting synthesis")
    completed_count: int = Field(..., description="Number of audio chunks ready for pickup")


class QueueItem(BaseModel):
    """An item in the synthesis queue."""

    text: str
    request_id: Optional[str] = None
