"""cici chat interface - Text and voice interaction with MIND API."""

import json
import os
import queue
import select
import threading
import time

import av
import numpy as np
import streamlit as st
from streamlit_webrtc import WebRtcMode, webrtc_streamer

from config import config
from mind_client import MindClient, ConnectionState
from mouth_client import MouthClient

# ------------------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------------------

@st.cache_data(ttl=60)
def check_mind_health(api_url: str) -> bool:
    """Check MIND health with 60-second cache."""
    try:
        import httpx
        with httpx.Client(timeout=config.timeouts.health_check) as http_client:
            resp = http_client.get(f"{api_url}/health")
            return resp.status_code == 200
    except Exception:
        return False

API_URL = st.session_state.get("api_url", config.mind_url)
EARS_WS_URL = config.ears_ws_url  # Debug mode controlled by EARS_DEBUG env var
MOUTH_URL = config.mouth_url
TARGET_SAMPLE_RATE = config.sample_rate

# ------------------------------------------------------------------------------
# Session State Initialization
# ------------------------------------------------------------------------------

if "client" not in st.session_state:
    st.session_state.client = MindClient(base_url=API_URL)

if "message_log" not in st.session_state:
    st.session_state.message_log = []

if "startup_attempted" not in st.session_state:
    st.session_state.startup_attempted = False

if "audio_ws_connected" not in st.session_state:
    st.session_state.audio_ws_connected = False

if "audio_processor" not in st.session_state:
    st.session_state.audio_processor = None

if "mouth_client" not in st.session_state:
    st.session_state.mouth_client = MouthClient(base_url=MOUTH_URL)

if "tts_audio_queue" not in st.session_state:
    st.session_state.tts_audio_queue = []

# Shorthand reference
client: MindClient = st.session_state.client
mouth: MouthClient = st.session_state.mouth_client


# ------------------------------------------------------------------------------
# Auto-connect on Startup
# ------------------------------------------------------------------------------

if not st.session_state.startup_attempted:
    st.session_state.startup_attempted = True
    if client.state == ConnectionState.DISCONNECTED:
        client.connect()


# ------------------------------------------------------------------------------
# Message Formatting
# ------------------------------------------------------------------------------

def format_message(msg: dict) -> str:
    """Format a single MIND API message for display."""
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
        lines.append(str(msg))

    return "\n".join(lines)


def format_response(resp: dict) -> str:
    """Format a MIND API response for display."""
    messages = resp.get("messages", [])
    if not messages:
        return ""

    formatted_msgs = []
    for msg in messages:
        formatted = format_message(msg)
        if formatted:
            formatted_msgs.append(formatted)

    return "\n".join(formatted_msgs)


def format_transcription(msg: str) -> str | None:
    """Format an EARS transcription message for display.

    Returns None for messages that should not be logged (e.g., debug).
    """
    try:
        data = json.loads(msg)
        msg_type = data.get("type", "")

        if msg_type == "transcription":
            text = data.get("text", "")
            is_final = data.get("final", False)
            status = "final" if is_final else "partial"
            return f"[EARS:{status}] {text}"
        elif msg_type == "listening":
            return "[EARS] listening..."
        elif msg_type == "error":
            return f"[EARS:error] {data.get('message', 'Unknown error')}"
        elif msg_type == "debug":
            return None  # Don't log debug messages
        else:
            return msg
    except json.JSONDecodeError:
        return msg


def add_to_log(msg: str):
    """Add a message to the log with timestamp."""
    timestamp = time.strftime("%H:%M:%S")
    st.session_state.message_log.append(f"[{timestamp}] {msg}")


# ------------------------------------------------------------------------------
# Text Input Handler
# ------------------------------------------------------------------------------

def send_text_command(text: str) -> None:
    """Send a text command to the MIND API."""
    if not text.strip():
        return

    if client.state != ConnectionState.CONNECTED:
        st.error("Not connected to server")
        return

    # Log the sent message
    add_to_log(f"> {text.strip()}")

    # Send to MIND API
    response = client.process_text(text.strip())

    if response:
        formatted = format_response(response)
        if formatted:
            add_to_log(formatted)
    else:
        error = client.error_message or "No response"
        add_to_log(f"Error: {error}")


# ------------------------------------------------------------------------------
# Audio Processor (streams to EARS via WebSocket)
# ------------------------------------------------------------------------------

class AudioProcessor:
    """Processes audio frames and forwards to WebSocket."""

    def __init__(self, websocket_url: str, chunk_duration_ms: int = None):
        self.websocket_url = websocket_url
        self.chunk_duration_ms = chunk_duration_ms or config.audio.chunk_duration_ms
        self.audio_queue: queue.Queue = queue.Queue()
        self.message_queue: queue.Queue = queue.Queue()  # For messages to main thread
        self.running = False
        self.ws_thread = None
        # Buffer for accumulating audio samples (Int16 = 2 bytes per sample)
        self.sample_buffer = bytearray()
        self.target_bytes = int(TARGET_SAMPLE_RATE * self.chunk_duration_ms / 1000) * 2

    def start(self):
        """Start the WebSocket connection in a background thread."""
        self.running = True
        self.ws_thread = threading.Thread(target=self._ws_loop, daemon=True)
        self.ws_thread.start()

    def stop(self):
        """Stop the WebSocket connection."""
        self.flush_buffer()  # Send any remaining audio
        self.running = False

    def _add_message(self, msg: str):
        """Queue a message for the main thread to process."""
        timestamp = time.strftime("%H:%M:%S")
        self.message_queue.put(f"[{timestamp}] {msg}")

    def get_messages(self) -> list[str]:
        """Get all pending messages (called from main thread)."""
        messages = []
        while not self.message_queue.empty():
            try:
                messages.append(self.message_queue.get_nowait())
            except queue.Empty:
                break
        return messages

    def _ws_loop(self):
        """Background thread for WebSocket communication."""
        import websockets.sync.client as ws_client

        try:
            # Disable keepalive ping - we're constantly streaming audio so connection is alive
            with ws_client.connect(self.websocket_url, ping_interval=None) as ws:
                self._add_message("[EARS connected]")

                while self.running:
                    # Send any queued audio
                    try:
                        audio_data = self.audio_queue.get(timeout=0.1)
                        ws.send(audio_data)
                    except queue.Empty:
                        pass

                    # Check for incoming messages using select
                    try:
                        readable, _, _ = select.select([ws.socket], [], [], 0.01)
                        while readable:
                            try:
                                msg = ws.recv()
                                formatted = format_transcription(msg)
                                if formatted is not None:
                                    self._add_message(formatted)
                            except Exception as recv_err:
                                self._add_message(f"[recv error] {recv_err}")
                                break
                            # Check if more messages available
                            readable, _, _ = select.select([ws.socket], [], [], 0)
                    except Exception as e:
                        if "connection" not in str(e).lower():
                            self._add_message(f"[select error] {e}")

        except Exception as e:
            self._add_message(f"[EARS error] {e}")
        finally:
            self._add_message("[EARS disconnected]")

    def send_audio(self, pcm_int16_bytes: bytes):
        """Queue audio data for sending (direct, no buffering)."""
        self.audio_queue.put(pcm_int16_bytes)

    def add_audio(self, pcm_int16_bytes: bytes):
        """Buffer audio and send when chunk reaches target size."""
        self.sample_buffer.extend(pcm_int16_bytes)
        while len(self.sample_buffer) >= self.target_bytes:
            chunk = bytes(self.sample_buffer[: self.target_bytes])
            self.audio_queue.put(chunk)
            del self.sample_buffer[: self.target_bytes]

    def flush_buffer(self):
        """Send any remaining buffered audio."""
        if self.sample_buffer:
            self.audio_queue.put(bytes(self.sample_buffer))
            self.sample_buffer.clear()


def process_audio_frame(frame: av.AudioFrame, processor: AudioProcessor) -> av.AudioFrame:
    """Process incoming audio frame and forward to EARS.

    Note: AudioResampler with format="s16" outputs int16 directly.
    aiortc/WebRTC delivers audio that resamples to int16, NOT float [-1,1].
    """
    # Always resample to ensure consistent s16 mono format
    resampler = av.AudioResampler(
        format="s16",
        layout="mono",
        rate=TARGET_SAMPLE_RATE,
    )
    frame = resampler.resample(frame)[0]

    # Convert to numpy array - s16 format gives us int16 directly
    audio_array = frame.to_ndarray()

    # Flatten if needed (resampler outputs shape (1, samples) for mono)
    if audio_array.ndim > 1:
        audio_array = audio_array.flatten()

    # Resampler with s16 format should give int16, but verify
    if audio_array.dtype != np.int16:
        audio_array = audio_array.astype(np.int16)

    processor.add_audio(audio_array.tobytes())
    return frame


# ------------------------------------------------------------------------------
# UI - Connection Status
# ------------------------------------------------------------------------------

if client.state == ConnectionState.ERROR:
    st.error(f"Connection failed: {client.error_message}")
    if st.button("Retry"):
        client.connect()
        st.rerun()

elif client.state == ConnectionState.DISCONNECTED:
    st.warning("Disconnected")
    if st.button("Connect"):
        client.connect()
        st.rerun()


# ------------------------------------------------------------------------------
# UI - Sidebar
# ------------------------------------------------------------------------------

with st.sidebar:
    st.header("Connection")
    st.text(f"MIND: {API_URL}")
    st.text(f"EARS: {EARS_WS_URL}")
    st.text(f"MOUTH: {MOUTH_URL}")

    if check_mind_health(API_URL):
        st.success("MIND online")
    else:
        st.error("MIND offline")

    if mouth.health_check():
        st.success("MOUTH online")
    else:
        st.warning("MOUTH offline")

    if client.state == ConnectionState.CONNECTED:
        st.caption(f"Mode: `{client.mode}`")
        if client.current_directory:
            st.caption(f"CWD: `{client.current_directory}`")

        if st.button("Disconnect", use_container_width=True):
            client.disconnect()
            st.session_state.message_log = []
            st.rerun()

    st.divider()

    if st.button("Clear Log", use_container_width=True):
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


# ------------------------------------------------------------------------------
# UI - Main Content (Tabs)
# ------------------------------------------------------------------------------

if client.state != ConnectionState.CONNECTED:
    st.stop()

# Input tabs
text_tab, audio_tab = st.tabs(["Text", "Audio"])

with text_tab:
    with st.form("command_form", clear_on_submit=True):
        cmd = st.text_area(
            "Command:",
            height=80,
            placeholder="e.g., ls minus la, git status (Ctrl+Enter to send)",
            label_visibility="collapsed",
        )
        if st.form_submit_button("Send", use_container_width=True):
            send_text_command(cmd)
            st.rerun()

with audio_tab:
    # Get or create processor (must persist across reruns)
    if st.session_state.audio_processor is None:
        st.session_state.audio_processor = AudioProcessor(EARS_WS_URL)

    processor = st.session_state.audio_processor

    # Capture processor in closure (processor variable is from session_state above)
    _processor = processor  # Local reference for closure

    def frame_callback(frame: av.AudioFrame) -> av.AudioFrame:
        if _processor and _processor.running:
            return process_audio_frame(frame, _processor)
        return frame

    ctx = webrtc_streamer(
        key="audio-chat",
        mode=WebRtcMode.SENDONLY,
        audio_frame_callback=frame_callback,
        media_stream_constraints={
            "audio": {
                "echoCancellation": config.audio.echo_cancellation,
                "noiseSuppression": config.audio.noise_suppression,
                "autoGainControl": config.audio.auto_gain_control,
                "sampleRate": TARGET_SAMPLE_RATE,
                "channelCount": 1,
            },
            "video": False,
        },
        rtc_configuration={
            "iceServers": [{"urls": config.webrtc.ice_servers}]
        },
    )

    # Handle connection state changes
    if ctx.state.playing:
        if not st.session_state.audio_ws_connected:
            st.session_state.audio_processor.start()
            st.session_state.audio_ws_connected = True
    else:
        if st.session_state.audio_ws_connected:
            st.session_state.audio_processor.stop()
            st.session_state.audio_ws_connected = False
            # Create fresh processor for next session
            st.session_state.audio_processor = AudioProcessor(EARS_WS_URL)

# ------------------------------------------------------------------------------
# Polling and Audio Playback
# ------------------------------------------------------------------------------

def estimate_wav_duration(wav_bytes: bytes) -> float:
    """Estimate WAV duration in seconds from byte size.

    Assumes: 16kHz sample rate, 16-bit (2 bytes/sample), mono.
    WAV header is typically 44 bytes.
    """
    audio_bytes = len(wav_bytes) - 44
    bytes_per_second = 16000 * 2  # sample_rate * bytes_per_sample
    return max(0.5, audio_bytes / bytes_per_second)

# Poll for messages from audio processor
if st.session_state.audio_processor:
    new_messages = st.session_state.audio_processor.get_messages()
    if new_messages:
        st.session_state.message_log.extend(new_messages)

# Poll for MIND responses (during audio mode)
if st.session_state.audio_ws_connected:
    mind_response = client.poll_messages()
    if mind_response and mind_response.get("messages"):
        formatted = format_response(mind_response)
        if formatted:
            add_to_log(formatted)

# Poll for TTS audio (during audio mode only)
if st.session_state.audio_ws_connected:
    audio_bytes, metadata = mouth.get_next_audio()
    if audio_bytes:
        st.session_state.tts_audio_queue.append(audio_bytes)

# Play TTS audio if queued
audio_duration = 0.0
if st.session_state.tts_audio_queue:
    audio_bytes = st.session_state.tts_audio_queue.pop(0)
    audio_duration = estimate_wav_duration(audio_bytes)
    st.audio(audio_bytes, format="audio/wav", autoplay=True)

# Display message log
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

# Auto-refresh while audio streaming
if st.session_state.audio_ws_connected:
    if audio_duration > 0:
        # Wait for audio to finish before refreshing
        time.sleep(audio_duration + 0.2)
    else:
        time.sleep(1.0)
    st.rerun()
