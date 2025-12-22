"""cici audio interface - Voice-based interaction via EARS transcription."""

import queue
import threading
import time
from typing import Callable

import av
import numpy as np
import streamlit as st
from streamlit_webrtc import WebRtcMode, webrtc_streamer

from utils.audio_streamer import AudioStreamerConfig

# ------------------------------------------------------------------------------
# Configuration (same as testing page)
# ------------------------------------------------------------------------------

DEFAULT_WS_URL = "ws://localhost:8766"

# Target format for EARS
TARGET_SAMPLE_RATE = 16000


# ------------------------------------------------------------------------------
# Session State Initialization
# ------------------------------------------------------------------------------

if "audio_message_log" not in st.session_state:
    st.session_state.audio_message_log = []

if "audio_ws_connected" not in st.session_state:
    st.session_state.audio_ws_connected = False


# ------------------------------------------------------------------------------
# Audio Processor (streams to EARS via WebSocket)
# ------------------------------------------------------------------------------

class AudioProcessor:
    """Processes audio frames and forwards to WebSocket."""

    def __init__(self, websocket_url: str, message_callback: Callable[[str], None]):
        self.websocket_url = websocket_url
        self.message_callback = message_callback
        self.audio_queue: queue.Queue = queue.Queue()
        self.running = False
        self.ws_thread = None

    def start(self):
        """Start the WebSocket connection in a background thread."""
        self.running = True
        self.ws_thread = threading.Thread(target=self._ws_loop, daemon=True)
        self.ws_thread.start()

    def stop(self):
        """Stop the WebSocket connection."""
        self.running = False

    def _ws_loop(self):
        """Background thread for WebSocket communication."""
        import websockets.sync.client as ws_client

        try:
            with ws_client.connect(self.websocket_url) as ws:
                self.message_callback("[connected]")

                while self.running:
                    # Send any queued audio
                    try:
                        audio_data = self.audio_queue.get(timeout=0.1)
                        ws.send(audio_data)
                    except queue.Empty:
                        pass

                    # Check for incoming messages (non-blocking)
                    try:
                        ws.socket.setblocking(False)
                        msg = ws.recv()
                        self.message_callback(msg)
                    except BlockingIOError:
                        pass
                    except Exception:
                        pass
                    finally:
                        ws.socket.setblocking(True)

        except Exception as e:
            self.message_callback(f"[error] {e}")
        finally:
            self.message_callback("[disconnected]")

    def send_audio(self, pcm_int16_bytes: bytes):
        """Queue audio data for sending."""
        self.audio_queue.put(pcm_int16_bytes)


def process_audio_frame(frame: av.AudioFrame, processor: AudioProcessor) -> av.AudioFrame:
    """Process incoming audio frame and forward to EARS."""
    # Resample to target format if needed
    if frame.sample_rate != TARGET_SAMPLE_RATE:
        resampler = av.AudioResampler(
            format="s16",
            layout="mono",
            rate=TARGET_SAMPLE_RATE,
        )
        frame = resampler.resample(frame)[0]

    # Convert to numpy array
    audio_array = frame.to_ndarray()

    # Ensure mono
    if audio_array.ndim > 1:
        audio_array = audio_array.mean(axis=0)

    # Convert to int16 if not already
    if audio_array.dtype != np.int16:
        if audio_array.dtype in (np.float32, np.float64):
            audio_array = (audio_array * 32767).astype(np.int16)
        else:
            audio_array = audio_array.astype(np.int16)

    # Send to WebSocket
    processor.send_audio(audio_array.tobytes())

    return frame


# ------------------------------------------------------------------------------
# Message Handling
# ------------------------------------------------------------------------------

def add_message(msg: str):
    """Add a message to the log with timestamp."""
    timestamp = time.strftime("%H:%M:%S")
    st.session_state.audio_message_log.append(f"[{timestamp}] {msg}")


def format_transcription(msg: str) -> str:
    """Format a transcription message for display."""
    import json

    try:
        data = json.loads(msg)
        msg_type = data.get("type", "")

        if msg_type == "transcription":
            text = data.get("text", "")
            is_final = data.get("final", False)
            prefix = ">" if is_final else "..."
            return f"{prefix} {text}"
        elif msg_type == "listening":
            return "[listening]"
        elif msg_type == "error":
            return f"[error] {data.get('message', 'Unknown error')}"
        else:
            return msg
    except json.JSONDecodeError:
        return msg


# ------------------------------------------------------------------------------
# UI
# ------------------------------------------------------------------------------

st.title("Audio")

# Config in sidebar
with st.sidebar:
    st.header("Connection")
    ws_url = st.text_input("EARS WebSocket", value=DEFAULT_WS_URL)
    st.caption(f"Format: PCM Int16, {TARGET_SAMPLE_RATE}Hz, mono")

    st.divider()

    if st.button("Clear Log", use_container_width=True):
        st.session_state.audio_message_log = []
        st.rerun()

# Create processor with message callback
processor = AudioProcessor(ws_url, lambda msg: add_message(format_transcription(msg)))


def frame_callback(frame: av.AudioFrame) -> av.AudioFrame:
    return process_audio_frame(frame, processor)


# WebRTC streamer (minimalistic)
ctx = webrtc_streamer(
    key="audio",
    mode=WebRtcMode.SENDONLY,
    audio_frame_callback=frame_callback,
    media_stream_constraints={
        "audio": {
            "echoCancellation": True,
            "noiseSuppression": True,
            "autoGainControl": True,
            "sampleRate": TARGET_SAMPLE_RATE,
            "channelCount": 1,
        },
        "video": False,
    },
    rtc_configuration={
        "iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]
    },
)

# Handle connection state changes
if ctx.state.playing:
    if not st.session_state.audio_ws_connected:
        processor.start()
        st.session_state.audio_ws_connected = True
else:
    if st.session_state.audio_ws_connected:
        processor.stop()
        st.session_state.audio_ws_connected = False

# Message log display (same style as text page)
if st.session_state.audio_message_log:
    log_text = "\n\n".join(reversed(st.session_state.audio_message_log[-50:]))
    st.markdown("""
    <style>
    code {
        white-space: pre-wrap !important;
        word-wrap: break-word !important;
    }
    </style>
    """, unsafe_allow_html=True)
    st.code(log_text)
