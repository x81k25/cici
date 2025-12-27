"""
MIND - Logic and Routing FastAPI Service

A stateless REST API service that handles:
- Transcript buffering (word-by-word from EARS)
- Text processing (complete commands from FACE)
- Message buffering (responses for FACE to poll)
- Command routing (Ollama, CLI, Claude, Claude Code modes)

Endpoints:
    POST   /transcript     Buffer partial transcription from EARS, process on "execute"
    POST   /text           Process complete text input from FACE
    GET    /messages       Poll for response messages (FACE)
    GET    /health         Health check
"""

# standard library imports
import uuid
from contextlib import asynccontextmanager

# 3rd-party imports
from fastapi import FastAPI, HTTPException
from loguru import logger

# local imports
from mind.config import config
from mind.session import Session
from mind.transcript_buffer import TranscriptBuffer
from mind.message_buffer import MessageBuffer
from mind.input_processor import InputProcessor
from mind.command_router import CommandRouter
from mind.core.tts_client import send_to_tts, check_tts_health
from mind.core.sentence_detector import SentenceBuffer
from mind.schemas import (
    TranscriptRequest,
    TranscriptResponse,
    TextRequest,
    TextResponse,
    MessagesResponse,
    ErrorCodes,
)


# ------------------------------------------------------------------------------
# Globals
# ------------------------------------------------------------------------------

session: Session | None = None
transcript_buffer: TranscriptBuffer | None = None
message_buffer: MessageBuffer | None = None
input_processor: InputProcessor | None = None
command_router: CommandRouter | None = None


# ------------------------------------------------------------------------------
# Lifespan
# ------------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and cleanup resources."""
    global session, transcript_buffer, message_buffer, input_processor, command_router

    logger.info("starting MIND service")

    # initialize components
    command_router = CommandRouter()
    input_processor = InputProcessor()
    transcript_buffer = TranscriptBuffer()
    message_buffer = MessageBuffer()

    # create single persistent session
    session = Session(id="main")

    logger.info("MIND service ready")

    yield

    # cleanup
    logger.info("shutting down MIND service")
    if session:
        await session.cancel_active_tasks()
        session.cleanup()
    logger.info("MIND service shutdown complete")


# ------------------------------------------------------------------------------
# App
# ------------------------------------------------------------------------------

app = FastAPI(
    title="MIND - Logic and Routing Service",
    description="Stateless REST API for command processing and routing",
    version="0.2.0",
    lifespan=lifespan,
)


# ------------------------------------------------------------------------------
# Helper functions
# ------------------------------------------------------------------------------

async def dispatch_to_tts(text: str, request_id: str | None = None) -> None:
    """
    Dispatch text to TTS service using sentence detection.

    Splits text into sentences and sends each to TTS for synthesis.
    Fire-and-forget - does not block on TTS response.

    Args:
        text: Text to synthesize
        request_id: Optional request ID for tracing
    """
    if not text or not text.strip():
        return

    request_id = request_id or str(uuid.uuid4())
    sentence_buffer = SentenceBuffer()

    # add the full text and get sentences
    sentences = sentence_buffer.add(text)

    # flush any remaining content
    final = sentence_buffer.flush()
    if final:
        sentences.append(final)

    # dispatch each sentence to TTS
    for sentence in sentences:
        await send_to_tts(sentence, request_id)


async def process_command(text: str, original_voice: str | None = None) -> None:
    """
    Process a command and add the response to the message buffer.

    Args:
        text: The text to process.
        original_voice: Original voice transcription (for LLM fallback).
    """
    global session, input_processor, command_router, message_buffer

    try:
        # process the input
        input_result = await input_processor.process_text(text, session)

        # check for stop word
        if input_result.get("stop_detected"):
            await message_buffer.add({
                "type": "system",
                "content": "Command cancelled",
                "cancelled": True,
            })
            return

        # route the command
        translated = input_result.get("translated") or text
        route_result = await command_router.route(
            translated,
            session,
            original_voice=original_voice
        )

        # build message based on route result type
        result = route_result.get("result", {})
        route_type = route_result.get("type", "")

        # mode change responses
        if route_type in ("cli_enter", "ollama_enter", "claude_code_enter"):
            confirmation = route_result.get("confirmation", {})
            confirmation_msg = confirmation.get("message", "Mode changed")
            await message_buffer.add({
                "type": "system",
                "content": confirmation_msg,
                "mode_changed": True,
                "new_mode": session.interaction_mode,
            })
            # dispatch mode confirmation to TTS
            await dispatch_to_tts(confirmation_msg)

        # Ollama response
        elif route_type == "ollama":
            response_text = result.get("response")
            logger.info(f"adding Ollama response to message buffer: {response_text[:50] if response_text else ''}...")
            await message_buffer.add({
                "type": "llm_response",
                "content": response_text,
                "model": config.ollama_model,
                "success": result.get("success", False),
                "error": result.get("error"),
            })
            # dispatch Ollama response to TTS
            if result.get("success") and response_text:
                await dispatch_to_tts(response_text)

        # Claude response
        elif route_type == "claude":
            response_text = result.get("response")
            await message_buffer.add({
                "type": "llm_response",
                "content": response_text,
                "model": result.get("model", "claude-sonnet"),
                "success": result.get("success", False),
                "error": result.get("error"),
            })
            # dispatch Claude response to TTS
            if result.get("success") and response_text:
                await dispatch_to_tts(response_text)

        # Claude Code response
        elif route_type == "claude_code":
            response_text = result.get("response")
            await message_buffer.add({
                "type": "llm_response",
                "content": response_text,
                "model": result.get("model", "claude-code"),
                "success": result.get("success", False),
                "error": result.get("error"),
            })
            # dispatch Claude Code response to TTS
            if result.get("success") and response_text:
                await dispatch_to_tts(response_text)

        # CLI response
        elif route_type in ("cli", "trigger"):
            await message_buffer.add({
                "type": "cli_result",
                "command": result.get("command", ""),
                "output": result.get("output"),
                "exit_code": result.get("exit_code"),
                "success": result.get("success", False),
                "error": result.get("error"),
                "correction_attempted": result.get("correction_attempted", False),
                "original_command": result.get("original_command"),
                "corrected_command": result.get("corrected_command"),
            })
            # dispatch CLI summary to TTS if available
            summary = route_result.get("summary", {})
            summary_text = summary.get("summary") if summary else None
            if summary_text:
                await dispatch_to_tts(summary_text)

        # error response
        elif route_type == "error":
            await message_buffer.add({
                "type": "error",
                "content": route_result.get("message", "Unknown error"),
                "error": route_result.get("message"),
            })

    except Exception as e:
        logger.exception(f"error processing command: {e}")
        await message_buffer.add({
            "type": "error",
            "content": f"Processing error: {str(e)}",
            "error": str(e),
        })


# ------------------------------------------------------------------------------
# Transcript endpoint (from EARS)
# ------------------------------------------------------------------------------

@app.post("/transcript", response_model=TranscriptResponse)
async def receive_transcript(request: TranscriptRequest):
    """
    Receive partial transcription from EARS.

    Words are buffered until "execute" is received,
    then the full command is processed.
    """
    global transcript_buffer, session

    logger.info(f"received transcript from EARS: '{request.text}'")

    if session is None:
        raise HTTPException(
            status_code=503,
            detail={
                "code": ErrorCodes.SESSION_NOT_INITIALIZED,
                "message": "Session not initialized"
            }
        )

    # split text into words
    words = request.text.strip().split()

    for word in words:
        # check if this is the execute trigger
        if transcript_buffer.is_execute(word):
            # get the full command and process it
            command = await transcript_buffer.get_and_clear()

            if not command:
                return TranscriptResponse(
                    status="error",
                    command=None,
                    buffer=None,
                )

            # process the command asynchronously
            await process_command(command)

            return TranscriptResponse(
                status="processing",
                command=command,
                buffer=None,
            )

        # buffer the word
        await transcript_buffer.add_word(word)

    # return current buffer state
    return TranscriptResponse(
        status="buffered",
        buffer=transcript_buffer.words,
        command=None,
    )


# ------------------------------------------------------------------------------
# Text endpoint (from FACE)
# ------------------------------------------------------------------------------

@app.post("/text", response_model=TextResponse)
async def receive_text(request: TextRequest):
    """
    Receive complete text input from FACE.

    The text is processed immediately.
    """
    global session

    if session is None:
        raise HTTPException(
            status_code=503,
            detail={
                "code": ErrorCodes.SESSION_NOT_INITIALIZED,
                "message": "Session not initialized"
            }
        )

    try:
        # process the command
        await process_command(request.text, request.original_voice)

        return TextResponse(status="ok")

    except Exception as e:
        logger.exception(f"error processing text: {e}")
        return TextResponse(status="error", error=str(e))


# ------------------------------------------------------------------------------
# Messages endpoint (for FACE polling)
# ------------------------------------------------------------------------------

@app.get("/messages", response_model=MessagesResponse)
async def get_messages():
    """
    Get all buffered messages and clear the buffer.

    FACE calls this to poll for new responses.
    """
    global message_buffer, session

    logger.info(f"FACE polling /messages (buffer count: {message_buffer.count if message_buffer else 0})")

    if session is None:
        raise HTTPException(
            status_code=503,
            detail={
                "code": ErrorCodes.SESSION_NOT_INITIALIZED,
                "message": "Session not initialized"
            }
        )

    messages = await message_buffer.get_and_clear()

    return MessagesResponse(
        messages=messages,
        mode=session.interaction_mode,
        current_directory=session.current_directory,
    )


# ------------------------------------------------------------------------------
# Health check
# ------------------------------------------------------------------------------

@app.get("/health")
async def health():
    """Health check endpoint."""
    tts_healthy = await check_tts_health()
    return {
        "status": "healthy",
        "service": "mind",
        "mode": session.interaction_mode if session else None,
        "transcript_buffer": transcript_buffer.words if transcript_buffer else [],
        "pending_messages": message_buffer.count if message_buffer else 0,
        "tts_available": tts_healthy,
    }


# ------------------------------------------------------------------------------
# CLI entrypoint
# ------------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import uvicorn
    from mind.config import config

    parser = argparse.ArgumentParser(description="MIND logic and routing server")
    parser.add_argument("--host", default=config.mind_host, help="host to bind to")
    parser.add_argument("--port", type=int, default=config.mind_port, help="port to bind to")
    parser.add_argument("--reload", action="store_true", help="enable auto-reload")
    parser.add_argument("--debug", action="store_true", help="enable debug logging")

    args = parser.parse_args()

    if args.debug:
        import sys
        logger.remove()
        logger.add(sys.stderr, level="DEBUG")

    uvicorn.run(
        "mind.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
