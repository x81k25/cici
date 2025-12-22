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

    websocket_url: str = "ws://localhost:8766"
    chunk_duration_ms: int = 100


class AudioProcessor:
    """Processes audio frames and forwards to WebSocket."""

    def __init__(self, websocket_url: str, on_message: Callable[[str], None] | None = None):
        self.websocket_url = websocket_url
        self.on_message = on_message
        self.ws = None
        self.ws_thread = None
        self.audio_queue: queue.Queue = queue.Queue()
        self.running = False
        self.chunks_sent = 0
        self.bytes_sent = 0
        self._messages: list[str] = []

    def start(self):
        """Start the WebSocket connection in a background thread."""
        self.running = True
        self.ws_thread = threading.Thread(target=self._ws_loop, daemon=True)
        self.ws_thread.start()

    def stop(self):
        """Stop the WebSocket connection."""
        self.running = False
        if self.ws:
            try:
                asyncio.run(self.ws.close())
            except Exception:
                pass

    def _ws_loop(self):
        """Background thread for WebSocket communication."""
        import websockets.sync.client as ws_client

        try:
            with ws_client.connect(self.websocket_url) as ws:
                self.ws = ws
                self._messages.append("[connected]")

                while self.running:
                    # Send any queued audio
                    try:
                        audio_data = self.audio_queue.get(timeout=0.1)
                        ws.send(audio_data)
                        self.chunks_sent += 1
                        self.bytes_sent += len(audio_data)
                    except queue.Empty:
                        pass

                    # Check for incoming messages (non-blocking)
                    try:
                        ws.socket.setblocking(False)
                        msg = ws.recv()
                        self._messages.append(msg)
                        if self.on_message:
                            self.on_message(msg)
                    except BlockingIOError:
                        pass
                    except Exception:
                        pass
                    finally:
                        ws.socket.setblocking(True)

        except Exception as e:
            self._messages.append(f"[error] {e}")
        finally:
            self._messages.append("[disconnected]")

    def send_audio(self, pcm_int16_bytes: bytes):
        """Queue audio data for sending."""
        self.audio_queue.put(pcm_int16_bytes)

    def get_messages(self) -> list[str]:
        """Get and clear accumulated messages."""
        msgs = self._messages.copy()
        self._messages.clear()
        return msgs


def audio_frame_callback(frame: av.AudioFrame, processor: AudioProcessor) -> av.AudioFrame:
    """Process incoming audio frame and forward to EARS.

    Converts audio to PCM Int16 @ 16kHz mono format.
    """
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
        # Normalize float to int16 range
        if audio_array.dtype in (np.float32, np.float64):
            audio_array = (audio_array * 32767).astype(np.int16)
        else:
            audio_array = audio_array.astype(np.int16)

    # Send to WebSocket
    processor.send_audio(audio_array.tobytes())

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

    # Create processor
    processor = AudioProcessor(config.websocket_url)

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

        for msg in st.session_state.ws_messages[-10:]:  # Last 10 messages
            st.code(msg, language=None)
