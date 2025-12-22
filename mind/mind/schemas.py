# standard library imports
from typing import Literal, Any

# 3rd-party imports
from pydantic import BaseModel, Field


# ------------------------------------------------------------------------------
# Enums and literals
# ------------------------------------------------------------------------------

Role = Literal["client", "server"]
MessageType = Literal["session", "message", "error"]
InteractionMode = Literal["ollama", "cli", "claude_code"]


# ------------------------------------------------------------------------------
# Nested content models
# ------------------------------------------------------------------------------

class LLMResponse(BaseModel):
    """Response from an LLM (Ollama, Claude, Claude Code)."""
    success: bool
    content: str | None = Field(
        default=None,
        description="The LLM's response text"
    )
    model: str | None = Field(
        default=None,
        description="Model used for inference"
    )
    error: str | None = Field(
        default=None,
        description="Error message if request failed"
    )


class CLIResult(BaseModel):
    """Result from CLI command execution."""
    success: bool
    command: str = Field(
        description="The command that was executed"
    )
    output: str | None = Field(
        default=None,
        description="Command stdout/stderr output"
    )
    exit_code: int | None = Field(
        default=None,
        description="Process exit code"
    )
    error: str | None = Field(
        default=None,
        description="Error message if execution failed"
    )
    # LLM correction fields
    correction_attempted: bool = Field(
        default=False,
        description="Whether LLM correction was attempted"
    )
    original_command: str | None = Field(
        default=None,
        description="Original command before correction"
    )
    corrected_command: str | None = Field(
        default=None,
        description="LLM-corrected command if correction was applied"
    )


class ErrorDetail(BaseModel):
    """Structured error information."""
    code: str = Field(
        description="Error code for programmatic handling"
    )
    message: str = Field(
        description="Human-readable error message"
    )
    details: dict | None = Field(
        default=None,
        description="Additional error context"
    )


class InputEcho(BaseModel):
    """Echo of the processed input."""
    raw: str | None = Field(
        default=None,
        description="Original input text or transcription"
    )
    translated: str | None = Field(
        default=None,
        description="Voice-to-CLI translated command (if applicable)"
    )
    transcription: str | None = Field(
        default=None,
        description="Audio transcription (for audio input)"
    )


# ------------------------------------------------------------------------------
# Request models
# ------------------------------------------------------------------------------

class TranscriptRequest(BaseModel):
    """Request from EARS with partial transcription."""
    text: str = Field(description="Partial transcription (one or more words)")


class TextRequest(BaseModel):
    """Request from FACE with complete text input."""
    text: str = Field(description="The complete text to process")
    original_voice: str | None = Field(
        default=None,
        description="Original voice transcription (for LLM fallback)"
    )


# ------------------------------------------------------------------------------
# Response models
# ------------------------------------------------------------------------------

class TranscriptResponse(BaseModel):
    """Response for transcript word buffering."""
    status: str = Field(description="'buffered' or 'processing'")
    buffer: list[str] | None = Field(
        default=None,
        description="Current buffer contents (when status='buffered')"
    )
    command: str | None = Field(
        default=None,
        description="Full command being processed (when status='processing')"
    )


class TextResponse(BaseModel):
    """Response for text input."""
    status: str = Field(description="'ok' or 'error'")
    error: str | None = Field(
        default=None,
        description="Error message if status='error'"
    )


class Message(BaseModel):
    """A single message in the message buffer."""
    type: str = Field(description="Message type: 'llm_response', 'cli_result', 'error', 'system'")
    content: str | None = Field(default=None, description="Message content")
    model: str | None = Field(default=None, description="Model used (for LLM responses)")
    command: str | None = Field(default=None, description="Command executed (for CLI results)")
    output: str | None = Field(default=None, description="Command output (for CLI results)")
    exit_code: int | None = Field(default=None, description="Exit code (for CLI results)")
    error: str | None = Field(default=None, description="Error message")
    timestamp: str | None = Field(default=None, description="ISO timestamp")


class MessagesResponse(BaseModel):
    """Response containing buffered messages for FACE."""
    messages: list[dict[str, Any]] = Field(
        default_factory=list,
        description="List of messages"
    )
    mode: InteractionMode = Field(description="Current interaction mode")
    current_directory: str = Field(description="Current working directory")


class StatusResponse(BaseModel):
    """Simple status response."""
    status: str
    message: str | None = None


class ErrorResponse(BaseModel):
    """Error response."""
    error: ErrorDetail


# ------------------------------------------------------------------------------
# Error codes
# ------------------------------------------------------------------------------

class ErrorCodes:
    """Standard error codes for programmatic handling."""
    # Input errors
    INVALID_JSON = "invalid_json"
    INVALID_MESSAGE_TYPE = "invalid_message_type"
    MISSING_FIELD = "missing_field"
    EMPTY_BUFFER = "empty_buffer"

    # Execution errors
    COMMAND_BLOCKED = "command_blocked"
    COMMAND_FAILED = "command_failed"
    LLM_ERROR = "llm_error"
    LLM_TIMEOUT = "llm_timeout"
    TRANSCRIPTION_FAILED = "transcription_failed"

    # Internal errors
    INTERNAL_ERROR = "internal_error"
    SESSION_NOT_INITIALIZED = "session_not_initialized"
