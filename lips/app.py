"""cici frontend - UI for cici personal assistant."""

import json
import os
import time
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from mind_client import MindClient, ConnectionState

# ------------------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------------------

# Load environment variables from .env file
load_dotenv(Path(__file__).parent / ".env")

# Build API URL from environment
API_HOST = os.getenv("CICI_API_HOST", "localhost")
API_PORT = os.getenv("CICI_API_PORT", "8765")
API_SECURE = os.getenv("CICI_API_SECURE", "false").lower() == "true"
API_PROTOCOL = "https" if API_SECURE else "http"
API_URL = f"{API_PROTOCOL}://{API_HOST}:{API_PORT}"

# ------------------------------------------------------------------------------
# Streamlit Configuration
# ------------------------------------------------------------------------------

st.set_page_config(
    page_title="cici - text assistant",
    page_icon="terminal",
    layout="centered"
)

# ------------------------------------------------------------------------------
# Session State Initialization
# ------------------------------------------------------------------------------

if "client" not in st.session_state:
    st.session_state.client = MindClient(base_url=API_URL)

if "message_log" not in st.session_state:
    st.session_state.message_log = []

if "startup_attempted" not in st.session_state:
    st.session_state.startup_attempted = False

if "awaiting_response" not in st.session_state:
    st.session_state.awaiting_response = False

# Shorthand reference
client: MindClient = st.session_state.client


# ------------------------------------------------------------------------------
# Auto-connect on Startup
# ------------------------------------------------------------------------------

def find_rejoinable_session() -> str | None:
    """Check for existing session to rejoin.

    Returns:
        Session ID to rejoin, or None if no session available.
    """
    sessions = client.list_sessions()
    for sess in sessions:
        session_id = sess.get("session_id")
        if session_id:
            return session_id
    return None


if not st.session_state.startup_attempted:
    st.session_state.startup_attempted = True
    if client.state == ConnectionState.DISCONNECTED:
        # Check for existing session to rejoin
        existing_session = find_rejoinable_session()
        if existing_session:
            if client.join_session(existing_session):
                st.session_state.message_log.append(
                    f"--- Rejoined session {existing_session[:8]}... ---"
                )
        else:
            # Create new session
            client.create_session()


# ------------------------------------------------------------------------------
# Helper Functions
# ------------------------------------------------------------------------------

def format_response(resp: dict) -> str:
    """Format a response for display."""
    lines = []

    # Input echo
    input_data = resp.get("input", {})
    if input_data:
        raw = input_data.get("raw", "")
        translated = input_data.get("translated", "")
        if raw:
            lines.append(f"Input: {raw}")
        if translated and translated != raw:
            lines.append(f"Translated: {translated}")

    # Cancelled
    if resp.get("cancelled"):
        lines.append("CANCELLED")
        return "\n".join(lines)

    # LLM Response
    llm = resp.get("llm_response")
    if llm:
        if llm.get("success"):
            content = llm.get("content", "")
            model = llm.get("model", "")
            lines.append(f"[{model}] {content}")
        else:
            error = llm.get("error", "Unknown error")
            lines.append(f"LLM Error: {error}")

    # CLI Result
    cli = resp.get("cli_result")
    if cli:
        cmd = cli.get("command", "")
        lines.append(f"$ {cmd}")
        if cli.get("success"):
            output = cli.get("output", "")
            if output:
                lines.append(output)
            exit_code = cli.get("exit_code")
            if exit_code is not None and exit_code != 0:
                lines.append(f"(exit code: {exit_code})")
        else:
            error = cli.get("error", "Command failed")
            lines.append(f"Error: {error}")

        # Correction info
        if cli.get("correction_attempted"):
            orig = cli.get("original_command", "")
            corrected = cli.get("corrected_command", "")
            lines.append(f"Corrected: {orig} -> {corrected}")

    # Error
    error = resp.get("error")
    if error:
        code = error.get("code", "")
        msg = error.get("message", "Unknown error")
        lines.append(f"Error [{code}]: {msg}")

    return "\n".join(lines) if lines else json.dumps(resp, indent=2)


def send_text_command(text: str) -> None:
    """Send a text command to the server."""
    if not text.strip():
        return

    if client.state != ConnectionState.CONNECTED:
        st.error("Not connected to server")
        return

    # Log the sent message
    timestamp = time.strftime("%H:%M:%S")
    st.session_state.message_log.append(f"[{timestamp}] > {text.strip()}")

    # Send to MIND API
    response = client.process_text(text.strip())

    if response:
        formatted = format_response(response)
        st.session_state.message_log.append(f"[{timestamp}] {formatted}")
    else:
        error = client.error_message or "No response"
        st.session_state.message_log.append(f"[{timestamp}] Error: {error}")


# ------------------------------------------------------------------------------
# UI Components
# ------------------------------------------------------------------------------

# Show connection issues only when not connected
if client.state == ConnectionState.ERROR:
    error_msg = f"Connection failed: {client.error_message}"
    st.error(error_msg)

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Retry"):
            # Try to rejoin or create new session
            existing = find_rejoinable_session()
            if existing:
                client.join_session(existing)
            else:
                client.create_session()
            st.rerun()
    with col2:
        if st.button("New Session"):
            client.create_session()
            st.rerun()

elif client.state == ConnectionState.DISCONNECTED:
    st.warning("Disconnected")
    if st.button("Connect"):
        existing = find_rejoinable_session()
        if existing:
            client.join_session(existing)
        else:
            client.create_session()
        st.rerun()

# Sidebar with settings
with st.sidebar:
    st.header("Connection")
    st.text(f"Server: {API_URL}")

    # Health check indicator
    if client.health_check():
        st.success("Server online")
    else:
        st.error("Server offline")

    if client.state == ConnectionState.CONNECTED:
        st.caption(f"Session: `{client.session_id[:8] if client.session_id else '?'}...`")
        st.caption(f"Mode: `{client.mode}`")
        if client.current_directory:
            st.caption(f"CWD: `{client.current_directory}`")

        if st.button("Disconnect", use_container_width=True):
            client.disconnect(kill_session=False)
            st.session_state.message_log = []
            st.rerun()

    st.divider()

    # Sessions panel
    st.header("Sessions")

    sessions = client.list_sessions()

    if sessions:
        for sess in sessions:
            sid = sess.get("session_id", "?")
            mode = sess.get("mode", "?")
            idle = sess.get("idle_seconds", 0)
            is_current = client.session_id and sid == client.session_id

            # Format idle time
            if idle is None:
                idle_str = "?"
            elif idle < 60:
                idle_str = f"{idle:.0f}s"
            else:
                idle_str = f"{idle/60:.1f}m"

            with st.container():
                col1, col2 = st.columns([3, 1])
                with col1:
                    label = f"`{sid[:8]}` ({mode})"
                    if is_current:
                        label += " <- you"
                    st.markdown(label)
                    st.caption(f"idle: {idle_str}")
                with col2:
                    if not is_current:
                        if st.button("Join", key=f"join_{sid}", use_container_width=True):
                            client.disconnect(kill_session=False)
                            st.session_state.message_log = []
                            if not client.join_session(sid):
                                st.error(f"Failed to join: {client.error_message}")
                            st.rerun()
                    else:
                        if st.button("Kill", key=f"kill_{sid}", use_container_width=True):
                            client.kill_session(sid)
                            client.disconnect(kill_session=False)
                            st.rerun()

        st.divider()
        if st.button("Kill All Sessions", use_container_width=True, type="secondary"):
            client.kill_all_sessions()
            if client.state == ConnectionState.CONNECTED:
                client.disconnect(kill_session=False)
            st.rerun()
    else:
        st.caption("No active sessions")

    if st.button("Refresh", key="refresh_sessions", use_container_width=True):
        st.rerun()

    st.divider()

    st.header("Voice Syntax")
    st.markdown("""
    | say | get |
    |-----|-----|
    | minus | `-` |
    | slash | `/` |
    | dot | `.` |
    | pipe | `\\|` |
    | greater than | `>` |
    | tilde | `~` |
    """)

    st.divider()

    st.header("Mode Triggers")
    st.markdown("""
    **Ollama (chat):**
    - `chat mode`
    - `back to chat`

    **CLI (commands):**
    - `commands mode`
    - `cli mode`

    **Claude Code:**
    - `let's code`
    - `code mode`
    """)

# Only show main UI if connected
if client.state != ConnectionState.CONNECTED:
    st.stop()

# Command input form (Ctrl+Enter to submit)
with st.form("command_form", clear_on_submit=True):
    cmd = st.text_area(
        "Command:",
        height=80,
        placeholder="e.g., ls minus la, git status (Ctrl+Enter to send)",
        label_visibility="collapsed",
    )
    col1, col2 = st.columns([4, 1])
    with col1:
        if st.form_submit_button("Send", use_container_width=True):
            send_text_command(cmd)
            st.rerun()
    with col2:
        if st.form_submit_button("Cancel", use_container_width=True):
            client.cancel_tasks()
            st.rerun()

# Log output
if st.session_state.message_log:
    log_text = "\n\n".join(reversed(st.session_state.message_log[-50:]))
    st.markdown("""
    <style>
    code {
        white-space: pre-wrap !important;
        word-wrap: break-word !important;
    }
    </style>
    """, unsafe_allow_html=True)
    st.code(log_text)
