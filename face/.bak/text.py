"""cici text interface - Text-based interaction with MIND API."""

import time

import streamlit as st

from mind_client import MindClient, ConnectionState


# ------------------------------------------------------------------------------
# Page Configuration
# ------------------------------------------------------------------------------

# Get shared config from session state (set by app.py)
API_URL = st.session_state.get("api_url", "http://localhost:8765")

# ------------------------------------------------------------------------------
# Session State Initialization
# ------------------------------------------------------------------------------

if "client" not in st.session_state:
    st.session_state.client = MindClient(base_url=API_URL)

if "message_log" not in st.session_state:
    st.session_state.message_log = []

if "startup_attempted" not in st.session_state:
    st.session_state.startup_attempted = False

# Shorthand reference
client: MindClient = st.session_state.client


# ------------------------------------------------------------------------------
# Auto-connect on Startup
# ------------------------------------------------------------------------------

if not st.session_state.startup_attempted:
    st.session_state.startup_attempted = True
    if client.state == ConnectionState.DISCONNECTED:
        client.connect()


# ------------------------------------------------------------------------------
# Helper Functions
# ------------------------------------------------------------------------------

def format_message(msg: dict) -> str:
    """Format a single message for display."""
    msg_type = msg.get("type", "")
    lines = []

    if msg_type == "system":
        content = msg.get("content", "")
        if msg.get("mode_changed"):
            new_mode = msg.get("new_mode", "")
            lines.append(f"[System] {content} (mode: {new_mode})")
        elif msg.get("cancelled"):
            lines.append("[System] Command cancelled")
        else:
            lines.append(f"[System] {content}")

    elif msg_type == "llm_response":
        model = msg.get("model", "llm")
        content = msg.get("content", "")
        if msg.get("success") or content:
            lines.append(f"[{model}] {content}")
        else:
            error = msg.get("error", "Unknown error")
            lines.append(f"[{model}] Error: {error}")

    elif msg_type == "cli_result":
        cmd = msg.get("command", "")
        lines.append(f"$ {cmd}")

        if msg.get("correction_attempted"):
            orig = msg.get("original_command", "")
            corrected = msg.get("corrected_command", "")
            if orig and corrected:
                lines.append(f"(corrected: {orig} -> {corrected})")

        if msg.get("success"):
            output = msg.get("output", "")
            if output:
                lines.append(output)
            exit_code = msg.get("exit_code")
            if exit_code is not None and exit_code != 0:
                lines.append(f"(exit code: {exit_code})")
        else:
            error = msg.get("error", "Command failed")
            lines.append(f"Error: {error}")

    elif msg_type == "error":
        content = msg.get("content", msg.get("error", "Unknown error"))
        lines.append(f"[Error] {content}")

    else:
        # Unknown message type - show raw
        lines.append(str(msg))

    return "\n".join(lines)


def format_response(resp: dict) -> str:
    """Format a response (containing messages) for display."""
    messages = resp.get("messages", [])
    if not messages:
        return ""

    formatted_msgs = []
    for msg in messages:
        formatted = format_message(msg)
        if formatted:
            formatted_msgs.append(formatted)

    return "\n".join(formatted_msgs)


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
        if formatted:
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

    if st.button("Retry"):
        client.connect()
        st.rerun()

elif client.state == ConnectionState.DISCONNECTED:
    st.warning("Disconnected")
    if st.button("Connect"):
        client.connect()
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
        st.caption(f"Mode: `{client.mode}`")
        if client.current_directory:
            st.caption(f"CWD: `{client.current_directory}`")

        if st.button("Disconnect", use_container_width=True):
            client.disconnect()
            st.session_state.message_log = []
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
        if st.form_submit_button("Clear Log", use_container_width=True):
            st.session_state.message_log = []
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
