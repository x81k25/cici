"""Audio streamer component using streamlit-webrtc.

This module provides audio streaming to EARS via WebSocket using streamlit-webrtc,
which handles browser audio capture reliably across all browsers.

Audio Format (sent to EARS):
- Raw PCM Int16 (16-bit signed little-endian)
- 16000 Hz sample rate
- Mono (1 channel)
"""

import asyncio
import queue
import threading
from dataclasses import dataclass
from typing import Callable

import av
import numpy as np
import streamlit as st
from streamlit_webrtc import WebRtcMode, webrtc_streamer

# Target format for EARS
TARGET_SAMPLE_RATE = 16000
TARGET_CHANNELS = 1


@dataclass
class AudioStreamerConfig:
    """Configuration for the audio streamer component."""

    websocket_url: str = "ws://localhost:8766/?debug=true"
    chunk_duration_ms: int = 100


class AudioProcessor:
    """Processes audio frames and forwards to WebSocket."""

    def __init__(
        self,
        websocket_url: str,
        chunk_duration_ms: int = 100,
        on_message: Callable[[str], None] | None = None,
    ):
        self.websocket_url = websocket_url
        self.chunk_duration_ms = chunk_duration_ms
        self.on_message = on_message
        self.ws = None
        self.ws_thread = None
        self.audio_queue: queue.Queue = queue.Queue()
        self.running = False
        self.chunks_sent = 0
        self.bytes_sent = 0
        self._messages: list[str] = []
        # Buffer for accumulating audio samples (Int16 = 2 bytes per sample)
        self.sample_buffer = bytearray()
        self.target_bytes = int(TARGET_SAMPLE_RATE * chunk_duration_ms / 1000) * 2

    def start(self):
        """Start the WebSocket connection in a background thread."""
        self.running = True
        self.ws_thread = threading.Thread(target=self._ws_loop, daemon=True)
        self.ws_thread.start()

    def stop(self):
        """Stop the WebSocket connection."""
        self.flush_buffer()  # Send any remaining audio
        self.running = False
        if self.ws:
            try:
                asyncio.run(self.ws.close())
            except Exception:
                pass

    def _ws_loop(self):
        """Background thread for WebSocket communication."""
        import select
        import websockets.sync.client as ws_client

        try:
            with ws_client.connect(self.websocket_url) as ws:
                self.ws = ws
                self._messages.append("[connected]")

                while self.running:
                    # Send any queued audio
                    try:
                        audio_data = self.audio_queue.get(timeout=0.01)
                        ws.send(audio_data)
                        self.chunks_sent += 1
                        self.bytes_sent += len(audio_data)
                    except queue.Empty:
                        pass

                    # Check for incoming messages using select
                    try:
                        readable, _, _ = select.select([ws.socket], [], [], 0.01)
                        while readable:
                            msg = ws.recv()
                            self._messages.append(msg)
                            if self.on_message:
                                self.on_message(msg)
                            # Check if more messages available
                            readable, _, _ = select.select([ws.socket], [], [], 0)
                    except Exception as e:
                        if "connection" not in str(e).lower():
                            self._messages.append(f"[recv error] {e}")

        except Exception as e:
            self._messages.append(f"[error] {e}")
        finally:
            self._messages.append("[disconnected]")

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

    def get_messages(self) -> list[str]:
        """Get and clear accumulated messages."""
        msgs = self._messages.copy()
        self._messages.clear()
        return msgs


def audio_frame_callback(frame: av.AudioFrame, processor: AudioProcessor) -> av.AudioFrame:
    """Process incoming audio frame and forward to EARS.

    Converts audio to PCM Int16 @ 16kHz mono format.

    Note: AudioResampler with format="s16" outputs int16 directly.
    aiortc/WebRTC delivers audio that resamples to int16, NOT float [-1,1].
    See: https://github.com/whitphx/streamlit-webrtc
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
        # Unexpected format - convert safely
        audio_array = audio_array.astype(np.int16)

    # Buffer and send to WebSocket when chunk is full
    processor.add_audio(audio_array.tobytes())

    return frame


def render_audio_streamer(
    config: AudioStreamerConfig | None = None,
    height: int = 400,
) -> None:
    """Render the audio streamer component using streamlit-webrtc.

    Args:
        config: Streamer configuration. Uses defaults if not provided.
        height: Height hint (not directly used by webrtc_streamer).
    """
    if config is None:
        config = AudioStreamerConfig()

    st.markdown(f"**WebSocket:** `{config.websocket_url}`")
    st.markdown("**Format:** PCM Int16, 16kHz, mono")

    # Initialize processor in session state
    if "audio_processor" not in st.session_state:
        st.session_state.audio_processor = None

    if "ws_messages" not in st.session_state:
        st.session_state.ws_messages = []

    # Create processor with config
    processor = AudioProcessor(config.websocket_url, config.chunk_duration_ms)

    def frame_callback(frame: av.AudioFrame) -> av.AudioFrame:
        return audio_frame_callback(frame, processor)

    # WebRTC streamer
    ctx = webrtc_streamer(
        key="audio-streamer",
        mode=WebRtcMode.SENDONLY,
        audio_frame_callback=frame_callback,
        media_stream_constraints={
            "audio": {
                "echoCancellation": True,
                "noiseSuppression": True,
                "autoGainControl": True,
                "sampleRate": TARGET_SAMPLE_RATE,
                "channelCount": TARGET_CHANNELS,
            },
            "video": False,
        },
        rtc_configuration={
            "iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]
        },
    )

    # Handle connection state
    if ctx.state.playing:
        if st.session_state.audio_processor is None:
            processor.start()
            st.session_state.audio_processor = processor
            st.session_state.ws_messages = ["[started]"]
    else:
        if st.session_state.audio_processor is not None:
            st.session_state.audio_processor.stop()
            st.session_state.audio_processor = None

    # Display stats
    col1, col2 = st.columns(2)
    with col1:
        if st.session_state.audio_processor:
            st.metric("Chunks Sent", st.session_state.audio_processor.chunks_sent)
    with col2:
        if st.session_state.audio_processor:
            bytes_sent = st.session_state.audio_processor.bytes_sent
            if bytes_sent < 1024:
                st.metric("Bytes Sent", f"{bytes_sent} B")
            elif bytes_sent < 1024 * 1024:
                st.metric("Bytes Sent", f"{bytes_sent / 1024:.1f} KB")
            else:
                st.metric("Bytes Sent", f"{bytes_sent / (1024*1024):.2f} MB")

    # Display WebSocket messages
    with st.expander("WebSocket Messages", expanded=True):
        if st.session_state.audio_processor:
            new_msgs = st.session_state.audio_processor.get_messages()
            st.session_state.ws_messages.extend(new_msgs)

        # Show message count
        total_msgs = len(st.session_state.ws_messages)
        if total_msgs > 0:
            st.caption(f"Showing last 50 of {total_msgs} messages")

        for msg in st.session_state.ws_messages[-50:]:
            st.code(msg, language=None)
