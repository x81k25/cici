# standard library imports
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

# 3rd-party imports
from loguru import logger

# ------------------------------------------------------------------------------
# constants
# ------------------------------------------------------------------------------

LOGS_DIR = Path(__file__).parent.parent.parent / "logs"

# ------------------------------------------------------------------------------
# session storage (replaces st.session_state)
# ------------------------------------------------------------------------------

_sessions: dict[str, dict] = {}

# ------------------------------------------------------------------------------
# custom log levels
# ------------------------------------------------------------------------------

# add custom levels for input/command/output logging
logger.level("INPUT", no=25, color="<cyan>", icon=">>>")
logger.level("COMMAND", no=26, color="<yellow>", icon="$")
logger.level("OUTPUT", no=27, color="<green>", icon="<<<")


# ------------------------------------------------------------------------------
# session management
# ------------------------------------------------------------------------------

def create_session(session_id: str | None = None) -> str:
    """
    Create a new session with the given ID or generate one.

    Args:
        session_id: Optional session ID. If None, generates a new one.

    Returns:
        The session ID.
    """
    if session_id is None:
        session_id = str(uuid.uuid4())[:8]

    if session_id not in _sessions:
        _sessions[session_id] = {
            "ui_logs": [],
            "last_activity": datetime.now(),
            "logger_configured": False,
            "log_path": None,
            "handler_ids": [],
        }

    return session_id


def get_session(session_id: str) -> dict | None:
    """Get session data by ID."""
    return _sessions.get(session_id)


def remove_session(session_id: str) -> None:
    """Remove a session and clean up its resources."""
    if session_id in _sessions:
        session = _sessions[session_id]
        # remove logger handlers for this session
        for handler_id in session.get("handler_ids", []):
            try:
                logger.remove(handler_id)
            except ValueError:
                pass  # handler already removed
        del _sessions[session_id]


# ------------------------------------------------------------------------------
# session logger
# ------------------------------------------------------------------------------

def _create_ui_log_sink(session_id: str) -> Callable:
    """Create a custom sink that stores log messages for UI display."""
    def sink(message):
        session = _sessions.get(session_id)
        if session is None:
            return

        record = message.record
        formatted = f"{record['time'].strftime('%H:%M:%S')} | {record['level'].name:<8} | {record['message']}"
        session["ui_logs"].append(formatted)

        # keep only last 100 entries
        if len(session["ui_logs"]) > 100:
            session["ui_logs"] = session["ui_logs"][-100:]

    return sink


def get_session_logger(session_id: str):
    """
    Get a loguru logger configured for the given session.

    Each session gets its own log file based on timestamp and session ID.

    Args:
        session_id: The session ID to configure logging for.

    Returns:
        The configured logger instance bound to the session.
    """
    session = _sessions.get(session_id)
    if session is None:
        create_session(session_id)
        session = _sessions[session_id]

    if not session["logger_configured"]:
        # create logs directory if it doesn't exist
        LOGS_DIR.mkdir(exist_ok=True)

        # generate log filename: YYYYMMDD-HHMMSS_session_id.log
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        log_filename = f"{timestamp}_{session_id}.log"
        log_path = LOGS_DIR / log_filename
        session["log_path"] = str(log_path)

        # filter for this session
        def log_filter(record, sid=session_id):
            return record["extra"].get("session_id") == sid

        # add file handler
        file_handler_id = logger.add(
            log_path,
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {message}",
            level="DEBUG",
            filter=log_filter,
            rotation="10 MB",
            retention="7 days",
        )

        # add UI handler for session state storage
        ui_handler_id = logger.add(
            _create_ui_log_sink(session_id),
            format="{message}",
            level="DEBUG",
            filter=log_filter,
        )

        session["handler_ids"] = [file_handler_id, ui_handler_id]
        session["logger_configured"] = True

        # log session start
        session_logger = logger.bind(session_id=session_id)
        session_logger.info(f"Session started - log file: {log_filename}")

    # return logger bound to this session
    return logger.bind(session_id=session_id)


def get_ui_logs(session_id: str) -> list[str]:
    """Get the list of log entries for display in the UI."""
    session = _sessions.get(session_id)
    if session is None:
        return []
    return session.get("ui_logs", [])


# ------------------------------------------------------------------------------
# logging convenience functions
# ------------------------------------------------------------------------------

def log_debug(message: str, session_id: str) -> None:
    """Log a debug message for the given session."""
    get_session_logger(session_id).debug(message)


def log_info(message: str, session_id: str) -> None:
    """Log an info message for the given session."""
    get_session_logger(session_id).info(message)


def log_warning(message: str, session_id: str) -> None:
    """Log a warning message for the given session."""
    get_session_logger(session_id).warning(message)


def log_error(message: str, session_id: str) -> None:
    """Log an error message for the given session."""
    get_session_logger(session_id).error(message)


def log_exception(message: str, session_id: str) -> None:
    """Log an exception with traceback for the given session."""
    get_session_logger(session_id).exception(message)


def log_input(message: str, session_id: str) -> None:
    """Log user input with custom INPUT level."""
    get_session_logger(session_id).log("INPUT", message)


def log_command(message: str, session_id: str) -> None:
    """Log parsed command with custom COMMAND level."""
    get_session_logger(session_id).log("COMMAND", message)


def log_output(message: str, session_id: str) -> None:
    """Log command output with custom OUTPUT level."""
    get_session_logger(session_id).log("OUTPUT", message)


# ------------------------------------------------------------------------------
# activity tracking
# ------------------------------------------------------------------------------

def update_last_activity(session_id: str) -> None:
    """Update the last activity timestamp for the session."""
    session = _sessions.get(session_id)
    if session:
        session["last_activity"] = datetime.now()


def get_last_activity(session_id: str) -> datetime | None:
    """Get the last activity timestamp for the session."""
    session = _sessions.get(session_id)
    if session:
        return session.get("last_activity")
    return None


def is_session_stale(session_id: str, timeout_minutes: int = 30) -> bool:
    """
    Check if the session has been idle for longer than the timeout.

    Args:
        session_id: The session ID to check.
        timeout_minutes: Minutes of inactivity before session is considered stale.

    Returns:
        True if session is stale or doesn't exist.
    """
    last_activity = get_last_activity(session_id)
    if last_activity is None:
        return True  # session doesn't exist

    return datetime.now() - last_activity > timedelta(minutes=timeout_minutes)
