# standard library imports
from typing import Literal

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
    """Response from the LLM (Ollama)."""
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

class ProcessTextRequest(BaseModel):
    """Request to process text input."""
    text: str = Field(description="The text to process")
    original_voice: str | None = Field(
        default=None,
        description="Original voice transcription (for LLM fallback)"
    )


class CreateSessionRequest(BaseModel):
    """Request to create a new session."""
    pass  # No parameters needed


# ------------------------------------------------------------------------------
# Response models
# ------------------------------------------------------------------------------

class SessionResponse(BaseModel):
    """Response with session information."""
    session_id: str
    mode: InteractionMode
    current_directory: str | None = None
    created_at: str | None = None
    last_activity: str | None = None
    idle_seconds: float | None = None


class ProcessResponse(BaseModel):
    """Response from processing text input."""
    session_id: str
    mode: InteractionMode
    current_directory: str | None = None
    input: InputEcho | None = None
    llm_response: LLMResponse | None = None
    cli_result: CLIResult | None = None
    error: ErrorDetail | None = None
    cancelled: bool = False


class ErrorResponse(BaseModel):
    """Error response."""
    error: ErrorDetail


class StatusResponse(BaseModel):
    """Simple status response."""
    status: str
    killed: int | None = None


# ------------------------------------------------------------------------------
# Error codes
# ------------------------------------------------------------------------------

class ErrorCodes:
    """Standard error codes for programmatic handling."""
    # Session errors
    SESSION_NOT_FOUND = "session_not_found"
    SESSION_EXPIRED = "session_expired"
    SESSION_ACTIVE = "session_active"
    MAX_SESSIONS = "max_sessions_reached"

    # Input errors
    INVALID_JSON = "invalid_json"
    INVALID_MESSAGE_TYPE = "invalid_message_type"
    MISSING_FIELD = "missing_field"

    # Execution errors
    COMMAND_BLOCKED = "command_blocked"
    COMMAND_FAILED = "command_failed"
    LLM_ERROR = "llm_error"
    LLM_TIMEOUT = "llm_timeout"
    TRANSCRIPTION_FAILED = "transcription_failed"

    # Internal errors
    INTERNAL_ERROR = "internal_error"
