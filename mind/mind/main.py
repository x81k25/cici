"""
MIND - Logic and Routing FastAPI Service

A REST API service that handles:
- Session management
- Voice-to-CLI translation
- Command routing (Ollama, CLI, Claude, Claude Code modes)
- TTS output

Endpoints:
    POST   /sessions                  Create new session
    GET    /sessions                  List all sessions
    GET    /sessions/{id}             Get session state
    DELETE /sessions/{id}             Kill session
    POST   /sessions/{id}/process     Process text input
    POST   /sessions/{id}/cancel      Cancel active tasks
"""

# standard library imports
from contextlib import asynccontextmanager

# 3rd-party imports
from fastapi import FastAPI, HTTPException
from loguru import logger

# local imports
from mind.session import Session, SessionManager
from mind.input_processor import InputProcessor
from mind.command_router import CommandRouter
from mind.schemas import (
    ProcessTextRequest,
    SessionResponse,
    ProcessResponse,
    StatusResponse,
    ErrorResponse,
    ErrorDetail,
    ErrorCodes,
    InputEcho,
    LLMResponse,
    CLIResult,
)


# ------------------------------------------------------------------------------
# Globals
# ------------------------------------------------------------------------------

session_manager: SessionManager | None = None
input_processor: InputProcessor | None = None
command_router: CommandRouter | None = None


# ------------------------------------------------------------------------------
# Lifespan
# ------------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and cleanup resources."""
    global session_manager, input_processor, command_router

    logger.info("starting MIND service")

    # initialize components
    command_router = CommandRouter()
    session_manager = SessionManager(
        max_sessions=10,
        claude_code_controller=command_router.claude_code_controller
    )
    input_processor = InputProcessor()

    logger.info("MIND service ready")

    yield

    # cleanup
    logger.info("shutting down MIND service")
    # kill all sessions
    for session_id in list(session_manager.sessions.keys()):
        await session_manager.remove_session(session_id)
    logger.info("MIND service shutdown complete")


# ------------------------------------------------------------------------------
# App
# ------------------------------------------------------------------------------

app = FastAPI(
    title="MIND - Logic and Routing Service",
    description="REST API for session management, command routing, and controller execution",
    version="0.1.0",
    lifespan=lifespan,
)


# ------------------------------------------------------------------------------
# Session endpoints
# ------------------------------------------------------------------------------

@app.post("/sessions", response_model=SessionResponse)
async def create_session():
    """Create a new session."""
    session = await session_manager.create_session()
    if session is None:
        raise HTTPException(
            status_code=503,
            detail={
                "code": ErrorCodes.MAX_SESSIONS,
                "message": f"Maximum sessions ({session_manager.max_sessions}) reached"
            }
        )

    return SessionResponse(
        session_id=session.id,
        mode=session.interaction_mode,
        current_directory=session.current_directory,
        created_at=session.created_at.isoformat(),
        last_activity=session.last_activity.isoformat(),
    )


@app.get("/sessions", response_model=list[SessionResponse])
async def list_sessions():
    """List all sessions."""
    sessions = await session_manager.list_sessions()
    return [
        SessionResponse(
            session_id=s["session_id"],
            mode=s["mode"],
            current_directory=s["current_directory"],
            created_at=s["created_at"],
            last_activity=s["last_activity"],
            idle_seconds=s["idle_seconds"],
        )
        for s in sessions
    ]


@app.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str):
    """Get session state."""
    session = await session_manager.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": ErrorCodes.SESSION_NOT_FOUND,
                "message": f"Session {session_id} not found"
            }
        )

    return SessionResponse(
        session_id=session.id,
        mode=session.interaction_mode,
        current_directory=session.current_directory,
        created_at=session.created_at.isoformat(),
        last_activity=session.last_activity.isoformat(),
        idle_seconds=(session.last_activity - session.created_at).total_seconds(),
    )


@app.delete("/sessions/{session_id}", response_model=StatusResponse)
async def kill_session(session_id: str):
    """Kill a session."""
    removed = await session_manager.remove_session(session_id)
    if not removed:
        raise HTTPException(
            status_code=404,
            detail={
                "code": ErrorCodes.SESSION_NOT_FOUND,
                "message": f"Session {session_id} not found"
            }
        )

    return StatusResponse(status="ok")


@app.delete("/sessions", response_model=StatusResponse)
async def kill_all_sessions():
    """Kill all sessions."""
    count = session_manager.count
    for session_id in list(session_manager.sessions.keys()):
        await session_manager.remove_session(session_id)

    return StatusResponse(status="ok", killed=count)


# ------------------------------------------------------------------------------
# Processing endpoints
# ------------------------------------------------------------------------------

@app.post("/sessions/{session_id}/process", response_model=ProcessResponse)
async def process_text(session_id: str, request: ProcessTextRequest):
    """Process text input for a session."""
    session = await session_manager.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": ErrorCodes.SESSION_NOT_FOUND,
                "message": f"Session {session_id} not found"
            }
        )

    try:
        # process the input
        input_result = await input_processor.process_text(request.text, session)

        # check for stop word
        if input_result.get("stop_detected"):
            return ProcessResponse(
                session_id=session.id,
                mode=session.interaction_mode,
                current_directory=session.current_directory,
                input=InputEcho(
                    raw=input_result.get("original"),
                    translated=None,
                ),
                cancelled=True,
            )

        # route the command
        translated = input_result.get("translated") or request.text
        route_result = await command_router.route(
            translated,
            session,
            original_voice=request.original_voice
        )

        # build response based on route result type
        response = ProcessResponse(
            session_id=session.id,
            mode=session.interaction_mode,
            current_directory=session.current_directory,
            input=InputEcho(
                raw=input_result.get("original"),
                translated=input_result.get("translated"),
            ),
        )

        result = route_result.get("result", {})
        route_type = route_result.get("type", "")

        # mode change responses
        if route_type in ("cli_enter", "ollama_enter", "claude_code_enter"):
            confirmation = route_result.get("confirmation", {})
            response.llm_response = LLMResponse(
                success=True,
                content=confirmation.get("message", "Mode changed"),
                model="system",
            )

        # Ollama response
        elif route_type == "ollama":
            response.llm_response = LLMResponse(
                success=result.get("success", False),
                content=result.get("response"),
                model="phi3",
                error=result.get("error"),
            )

        # Claude response
        elif route_type == "claude":
            response.llm_response = LLMResponse(
                success=result.get("success", False),
                content=result.get("response"),
                model=result.get("model", "claude-sonnet"),
                error=result.get("error"),
            )

        # Claude Code response
        elif route_type == "claude_code":
            response.llm_response = LLMResponse(
                success=result.get("success", False),
                content=result.get("response"),
                model=result.get("model", "claude-code"),
                error=result.get("error"),
            )

        # CLI response
        elif route_type in ("cli", "trigger"):
            response.cli_result = CLIResult(
                success=result.get("success", False),
                command=result.get("command", ""),
                output=result.get("output"),
                exit_code=result.get("exit_code"),
                error=result.get("error"),
                correction_attempted=result.get("correction_attempted", False),
                original_command=result.get("original_command"),
                corrected_command=result.get("corrected_command"),
            )

        # error response
        elif route_type == "error":
            response.error = ErrorDetail(
                code=ErrorCodes.COMMAND_FAILED,
                message=route_result.get("message", "Unknown error"),
            )

        return response

    except Exception as e:
        logger.exception(f"error processing text: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "code": ErrorCodes.INTERNAL_ERROR,
                "message": str(e)
            }
        )


@app.post("/sessions/{session_id}/cancel", response_model=StatusResponse)
async def cancel_tasks(session_id: str):
    """Cancel active tasks for a session."""
    session = await session_manager.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": ErrorCodes.SESSION_NOT_FOUND,
                "message": f"Session {session_id} not found"
            }
        )

    cancelled = await session.cancel_active_tasks()
    return StatusResponse(status="ok", killed=cancelled)


# ------------------------------------------------------------------------------
# Health check
# ------------------------------------------------------------------------------

@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "mind",
        "sessions": session_manager.count if session_manager else 0,
    }


# ------------------------------------------------------------------------------
# CLI entrypoint
# ------------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(description="MIND logic and routing server")
    parser.add_argument("--host", default="0.0.0.0", help="host to bind to")
    parser.add_argument("--port", type=int, default=8765, help="port to bind to")
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
