"""Audio streamer component for browser-based audio capture with WebSocket transmission.

This module provides a reusable audio streaming component that:
- Captures audio via AudioWorklet API for raw PCM access
- Streams raw PCM Int16 chunks to server via WebSocket in real-time
- Supports configurable WebSocket URL, chunk duration, and audio constraints

Audio Format (sent to server):
- Raw PCM (no container)
- Int16 samples (16-bit signed little-endian)
- 16000 Hz sample rate
- Mono (1 channel)
"""

from dataclasses import dataclass


@dataclass
class AudioStreamerConfig:
    """Configuration for the audio streamer component."""

    # WebSocket settings
    websocket_url: str = "ws://localhost:8766"

    # Audio settings
    sample_rate: int = 16000  # EARS expects 16kHz
    chunk_duration_ms: int = 100  # send chunks every 100ms
    echo_cancellation: bool = True
    noise_suppression: bool = True
    auto_gain_control: bool = True


def _build_streamer_html(config: AudioStreamerConfig) -> str:
    """Build the HTML/JS component for audio streaming using AudioWorklet."""

    # Calculate samples per chunk
    samples_per_chunk = int(config.sample_rate * config.chunk_duration_ms / 1000)

    # WebSocket message log styles
    ws_log_styles = """
    .ws-log-section {
        margin-top: 20px;
        padding: 15px;
        background: #1a1a1a;
        border-radius: 6px;
        border: 1px solid #333;
    }
    .ws-log-title {
        font-size: 12px;
        color: #888;
        margin-bottom: 8px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .ws-log {
        font-family: monospace;
        font-size: 12px;
        max-height: 200px;
        overflow-y: auto;
        color: #0f0;
    }
    .ws-log-entry {
        padding: 4px 0;
        border-bottom: 1px solid #222;
        word-break: break-all;
    }
    .ws-log-entry:last-child {
        border-bottom: none;
    }
    .ws-log-time {
        color: #666;
        margin-right: 8px;
    }
    """

    return f"""
<style>
    .streamer-container {{
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        padding: 20px;
        background: #1e1e1e;
        border-radius: 8px;
        color: #fff;
    }}
    .status-row {{
        display: flex;
        align-items: center;
        gap: 20px;
        margin-bottom: 15px;
    }}
    .status {{
        display: flex;
        align-items: center;
        gap: 10px;
        font-size: 14px;
    }}
    .status-dot {{
        width: 12px;
        height: 12px;
        border-radius: 50%;
        background: #666;
    }}
    .status-dot.recording {{
        background: #ff4444;
        animation: pulse 1s infinite;
    }}
    .status-dot.connected {{
        background: #4CAF50;
    }}
    .status-dot.connecting {{
        background: #ff9800;
        animation: pulse 1s infinite;
    }}
    .status-dot.error {{
        background: #ff4444;
    }}
    @keyframes pulse {{
        0%, 100% {{ opacity: 1; }}
        50% {{ opacity: 0.5; }}
    }}
    .buttons {{
        display: flex;
        gap: 10px;
        margin-bottom: 20px;
    }}
    button {{
        padding: 10px 20px;
        border: none;
        border-radius: 4px;
        cursor: pointer;
        font-size: 14px;
        font-weight: 500;
        transition: background 0.2s;
    }}
    button:disabled {{
        opacity: 0.5;
        cursor: not-allowed;
    }}
    .btn-start {{
        background: #4CAF50;
        color: white;
    }}
    .btn-start:hover:not(:disabled) {{
        background: #45a049;
    }}
    .btn-stop {{
        background: #f44336;
        color: white;
    }}
    .btn-stop:hover:not(:disabled) {{
        background: #da190b;
    }}
    .info {{
        font-size: 12px;
        color: #888;
        margin-top: 15px;
    }}
    .info div {{
        margin: 5px 0;
    }}
    .chunk-count {{
        color: #4CAF50;
    }}
    .sent-count {{
        color: #2196F3;
    }}
    .bytes-sent {{
        color: #9C27B0;
    }}
    .error {{
        color: #ff4444;
        margin-top: 10px;
    }}
    .ws-url {{
        font-size: 11px;
        color: #666;
        font-family: monospace;
    }}
    .format-info {{
        font-size: 11px;
        color: #4CAF50;
        font-family: monospace;
    }}
    {ws_log_styles}
</style>

<div class="streamer-container">
    <div class="status-row">
        <div class="status">
            <div class="status-dot" id="recordStatusDot"></div>
            <span id="recordStatusText">Ready</span>
        </div>
        <div class="status">
            <div class="status-dot" id="wsStatusDot"></div>
            <span id="wsStatusText">Disconnected</span>
        </div>
    </div>

    <div class="buttons">
        <button class="btn-start" id="startBtn" onclick="startStreaming()">Start Streaming</button>
        <button class="btn-stop" id="stopBtn" onclick="stopStreaming()" disabled>Stop Streaming</button>
    </div>

    <div class="info">
        <div>Chunks sent: <span class="sent-count" id="sentCount">0</span></div>
        <div>Bytes sent: <span class="bytes-sent" id="bytesSent">0</span></div>
        <div>Duration: <span id="duration">0.0s</span></div>
        <div class="format-info">Format: PCM Int16, {config.sample_rate}Hz, mono</div>
        <div class="ws-url">WebSocket: {config.websocket_url}</div>
    </div>

    <div id="errorMsg" class="error"></div>

    <div class="ws-log-section">
        <div class="ws-log-title">WebSocket Messages</div>
        <div id="wsLog" class="ws-log"></div>
    </div>
</div>

<script>
    // AudioWorklet processor code - will be loaded as data URL (fixes Firefox MIME type issue)
    const WORKLET_PROCESSOR_CODE = `
class PCMProcessor extends AudioWorkletProcessor {{
    constructor() {{
        super();
        this.bufferSize = SAMPLES_PER_CHUNK_PLACEHOLDER;
        this.buffer = new Float32Array(this.bufferSize);
        this.bufferIndex = 0;
    }}

    process(inputs, outputs, parameters) {{
        const input = inputs[0];
        if (input && input.length > 0) {{
            const channelData = input[0];
            for (let i = 0; i < channelData.length; i++) {{
                this.buffer[this.bufferIndex++] = channelData[i];
                if (this.bufferIndex >= this.bufferSize) {{
                    this.port.postMessage({{ type: 'audio', samples: this.buffer.slice() }});
                    this.bufferIndex = 0;
                }}
            }}
        }}
        return true;
    }}
}}
registerProcessor('pcm-processor', PCMProcessor);
`.replace('SAMPLES_PER_CHUNK_PLACEHOLDER', '{samples_per_chunk}');

    // Configuration for worklet
    const SAMPLES_PER_CHUNK = {samples_per_chunk};

    // State
    let audioContext = null;
    let workletNode = null;
    let mediaStream = null;
    let websocket = null;
    let startTime = null;
    let durationInterval = null;
    let chunksSent = 0;
    let totalBytesSent = 0;

    // Configuration
    const WEBSOCKET_URL = "{config.websocket_url}";
    const SAMPLE_RATE = {config.sample_rate};
    const AUDIO_CONSTRAINTS = {{
        echoCancellation: {str(config.echo_cancellation).lower()},
        noiseSuppression: {str(config.noise_suppression).lower()},
        autoGainControl: {str(config.auto_gain_control).lower()},
        channelCount: 1,  // mono
        sampleRate: SAMPLE_RATE
    }};

    // DOM elements
    const recordStatusDot = document.getElementById('recordStatusDot');
    const recordStatusText = document.getElementById('recordStatusText');
    const wsStatusDot = document.getElementById('wsStatusDot');
    const wsStatusText = document.getElementById('wsStatusText');
    const startBtn = document.getElementById('startBtn');
    const stopBtn = document.getElementById('stopBtn');
    const sentCount = document.getElementById('sentCount');
    const bytesSent = document.getElementById('bytesSent');
    const duration = document.getElementById('duration');
    const errorMsg = document.getElementById('errorMsg');
    const wsLog = document.getElementById('wsLog');

    function logWsMessage(data) {{
        const time = new Date().toLocaleTimeString('en-US', {{ hour12: false }});
        const entry = document.createElement('div');
        entry.className = 'ws-log-entry';
        entry.innerHTML = '<span class="ws-log-time">' + time + '</span>' + data;
        wsLog.appendChild(entry);
        wsLog.scrollTop = wsLog.scrollHeight;
    }}

    function updateRecordStatus(text, isRecording) {{
        recordStatusText.textContent = text;
        recordStatusDot.classList.remove('recording');
        if (isRecording) {{
            recordStatusDot.classList.add('recording');
        }}
    }}

    function updateWsStatus(text, state) {{
        wsStatusText.textContent = text;
        wsStatusDot.classList.remove('connected', 'connecting', 'error');
        if (state) {{
            wsStatusDot.classList.add(state);
        }}
    }}

    function showError(msg) {{
        errorMsg.textContent = msg;
        console.error('[AudioStreamer]', msg);
    }}

    function clearError() {{
        errorMsg.textContent = '';
    }}

    function updateDuration() {{
        if (startTime) {{
            const elapsed = (Date.now() - startTime) / 1000;
            duration.textContent = elapsed.toFixed(1) + 's';
        }}
    }}

    function formatBytes(bytes) {{
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
        return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
    }}

    function connectWebSocket() {{
        return new Promise((resolve, reject) => {{
            updateWsStatus('Connecting...', 'connecting');

            try {{
                websocket = new WebSocket(WEBSOCKET_URL);
                websocket.binaryType = 'arraybuffer';

                websocket.onopen = () => {{
                    console.log('[AudioStreamer] WebSocket connected');
                    updateWsStatus('Connected', 'connected');
                    logWsMessage('[connected]');
                    resolve();
                }};

                websocket.onclose = (event) => {{
                    console.log('[AudioStreamer] WebSocket closed:', event.code, event.reason);
                    updateWsStatus('Disconnected', null);
                    logWsMessage('[disconnected] code=' + event.code);
                    websocket = null;
                }};

                websocket.onerror = (error) => {{
                    console.error('[AudioStreamer] WebSocket error:', error);
                    updateWsStatus('Error', 'error');
                    logWsMessage('[error] connection failed');
                    showError('WebSocket connection failed. Is the server running?');
                    reject(error);
                }};

                websocket.onmessage = (event) => {{
                    console.log('[AudioStreamer] Server message:', event.data);
                    logWsMessage(event.data);
                }};

            }} catch (err) {{
                updateWsStatus('Error', 'error');
                reject(err);
            }}
        }});
    }}

    function disconnectWebSocket() {{
        if (websocket) {{
            websocket.close();
            websocket = null;
        }}
        updateWsStatus('Disconnected', null);
    }}

    function float32ToInt16(float32Array) {{
        // Convert Float32 [-1, 1] to Int16 [-32768, 32767]
        const int16Array = new Int16Array(float32Array.length);
        for (let i = 0; i < float32Array.length; i++) {{
            // Clamp to [-1, 1] range
            const s = Math.max(-1, Math.min(1, float32Array[i]));
            // Convert to Int16
            int16Array[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
        }}
        return int16Array;
    }}

    function sendAudioChunk(float32Samples) {{
        if (websocket && websocket.readyState === WebSocket.OPEN) {{
            // Convert to Int16 PCM
            const int16Samples = float32ToInt16(float32Samples);
            const bytes = int16Samples.buffer;

            websocket.send(bytes);
            chunksSent++;
            totalBytesSent += bytes.byteLength;

            sentCount.textContent = chunksSent;
            bytesSent.textContent = formatBytes(totalBytesSent);

            console.log(`[AudioStreamer] Sent chunk ${{chunksSent}}: ${{bytes.byteLength}} bytes`);
        }} else {{
            console.warn('[AudioStreamer] WebSocket not open, chunk not sent');
        }}
    }}

    async function startStreaming() {{
        clearError();
        chunksSent = 0;
        totalBytesSent = 0;
        sentCount.textContent = '0';
        bytesSent.textContent = '0';
        wsLog.innerHTML = '';

        // Connect WebSocket first
        try {{
            await connectWebSocket();
        }} catch (err) {{
            showError('Failed to connect to server: ' + (err.message || 'Connection refused'));
            return;
        }}

        // Start audio capture with AudioWorklet
        try {{
            // Create AudioContext with target sample rate
            audioContext = new AudioContext({{ sampleRate: SAMPLE_RATE }});

            // Log actual sample rate (browser may not support requested rate)
            console.log(`[AudioStreamer] AudioContext sample rate: ${{audioContext.sampleRate}}Hz`);
            if (audioContext.sampleRate !== SAMPLE_RATE) {{
                console.warn(`[AudioStreamer] Requested ${{SAMPLE_RATE}}Hz but got ${{audioContext.sampleRate}}Hz`);
            }}

            // Load worklet processor via Blob URL with correct MIME type
            const blob = new Blob([WORKLET_PROCESSOR_CODE], {{ type: 'application/javascript' }});
            const workletUrl = URL.createObjectURL(blob);
            await audioContext.audioWorklet.addModule(workletUrl);
            URL.revokeObjectURL(workletUrl);

            // Get microphone stream
            mediaStream = await navigator.mediaDevices.getUserMedia({{
                audio: AUDIO_CONSTRAINTS
            }});

            // Create audio source from microphone
            const source = audioContext.createMediaStreamSource(mediaStream);

            // Create worklet node
            workletNode = new AudioWorkletNode(audioContext, 'pcm-processor');

            // Handle audio data from worklet
            workletNode.port.onmessage = (event) => {{
                if (event.data.type === 'audio') {{
                    sendAudioChunk(event.data.samples);
                }}
            }};

            // Connect: microphone -> worklet
            source.connect(workletNode);
            // Don't connect to destination (we don't want to hear ourselves)

            startTime = Date.now();
            durationInterval = setInterval(updateDuration, 100);

            updateRecordStatus('Recording...', true);
            startBtn.disabled = true;
            stopBtn.disabled = false;

            console.log('[AudioStreamer] Streaming started (AudioWorklet, PCM Int16)');

        }} catch (err) {{
            disconnectWebSocket();
            cleanupAudio();

            if (err.name === 'NotAllowedError') {{
                showError('Microphone permission denied. Please allow access and try again.');
            }} else if (err.name === 'NotFoundError') {{
                showError('No microphone found. Please connect a microphone.');
            }} else if (err.name === 'NotSupportedError') {{
                showError('AudioWorklet not supported. Please use a modern browser (Chrome, Firefox, Edge).');
            }} else {{
                showError('Error accessing microphone: ' + err.message);
            }}
            updateRecordStatus('Error', false);
        }}
    }}

    function cleanupAudio() {{
        if (workletNode) {{
            workletNode.disconnect();
            workletNode = null;
        }}
        if (mediaStream) {{
            mediaStream.getTracks().forEach(track => track.stop());
            mediaStream = null;
        }}
        if (audioContext) {{
            audioContext.close();
            audioContext = null;
        }}
    }}

    function stopStreaming() {{
        clearInterval(durationInterval);
        cleanupAudio();
        disconnectWebSocket();

        updateRecordStatus('Stopped', false);
        startBtn.disabled = false;
        stopBtn.disabled = true;

        console.log('[AudioStreamer] Streaming stopped');
    }}

    // Browser compatibility checks
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {{
        showError('Your browser does not support audio recording. Please use Chrome, Firefox, or Safari.');
        startBtn.disabled = true;
    }}

    if (typeof AudioWorkletNode === 'undefined') {{
        showError('AudioWorklet not supported. Please use Chrome, Firefox, or Edge.');
        startBtn.disabled = true;
    }}
</script>
"""


def render_audio_streamer(
    config: AudioStreamerConfig | None = None,
    height: int = 400,
) -> None:
    """Render the audio streamer component.

    Args:
        config: Streamer configuration. Uses defaults if not provided.
        height: Height of the component in pixels.
    """
    import streamlit as st

    if config is None:
        config = AudioStreamerConfig()

    html = _build_streamer_html(config)
    st.components.v1.html(html, height=height)
