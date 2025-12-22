"""Testing page - Audio capture benchmarks."""

import streamlit as st

from utils.audio_recorder import AudioRecorderConfig, render_audio_recorder
from utils.audio_streamer import AudioStreamerConfig, render_audio_streamer

# ------------------------------------------------------------------------------
# Page Configuration
# ------------------------------------------------------------------------------

st.title("Audio Testing")

# Benchmark selector
benchmark = st.selectbox(
    "Select Benchmark",
    ["Benchmark 1: Local Recording", "Benchmark 2: WebSocket Streaming"],
    index=1,
)

st.divider()

# ------------------------------------------------------------------------------
# Benchmark 1: Local Recording & Playback
# ------------------------------------------------------------------------------

if benchmark == "Benchmark 1: Local Recording":
    st.caption("Local Recording & Playback")

    config = AudioRecorderConfig(
        chunk_duration_ms=500,
        echo_cancellation=True,
        noise_suppression=True,
        auto_gain_control=True,
        mono=True,
    )

    render_audio_recorder(config=config, height=400)

    with st.expander("Testing Instructions"):
        st.markdown("""
        **Benchmark 1: Local Recording & Playback**

        1. Click "Start Recording" to begin capturing audio
        2. Speak into your microphone for 10+ seconds
        3. Click "Stop Recording" when done
        4. Recording auto-downloads to your Downloads folder
        5. Use the audio player to verify playback quality

        **What to verify:**
        - Chunks are created every 500ms (check browser console)
        - Playback sounds clear without distortion
        - File downloads with timestamp filename
        """)

# ------------------------------------------------------------------------------
# Benchmark 2: WebSocket Streaming
# ------------------------------------------------------------------------------

elif benchmark == "Benchmark 2: WebSocket Streaming":
    st.caption("WebSocket Transmission")

    # Configuration sidebar
    with st.expander("Configuration", expanded=False):
        ws_host = st.text_input("WebSocket Host", value="localhost")
        ws_port = st.number_input("WebSocket Port", value=8766, min_value=1, max_value=65535)

    ws_url = f"ws://{ws_host}:{ws_port}/?debug=true"

    config = AudioStreamerConfig(websocket_url=ws_url)

    render_audio_streamer(config=config)

    with st.expander("Testing Instructions"):
        st.markdown(f"""
        **Benchmark 2: WebSocket Streaming (via streamlit-webrtc)**

        **Prerequisites:**
        - EARS service running on `{ws_url}`

        **Testing Steps:**
        1. Click "START" to begin streaming
        2. Grant microphone permission when prompted
        3. Speak into your microphone
        4. Watch "Chunks Sent" counter increment
        5. Check WebSocket Messages for transcription responses
        6. Click "STOP" when done

        **What to verify:**
        - Chunks Sent counter increments steadily
        - "[connected]" appears in WebSocket Messages
        - Transcription messages appear after speaking

        **Audio Format:**
        - Raw PCM Int16, 16kHz, mono
        - Converted from WebRTC audio stream

        **Current Config:**
        - WebSocket URL: `{ws_url}`
        - Sample rate: 16000 Hz
        """)
