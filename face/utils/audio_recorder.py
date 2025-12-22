"""Audio recorder component for browser-based audio capture.

This module provides a reusable audio recording component that:
- Captures audio via MediaRecorder API
- Auto-downloads recordings via browser
- Supports configurable chunk duration and audio constraints
"""

from dataclasses import dataclass

import streamlit as st


@dataclass
class AudioRecorderConfig:
    """Configuration for the audio recorder component."""

    chunk_duration_ms: int = 500
    echo_cancellation: bool = True
    noise_suppression: bool = True
    auto_gain_control: bool = True
    mono: bool = True


def _build_recorder_html(config: AudioRecorderConfig) -> str:
    """Build the HTML/JS component for audio recording."""
    return f"""
<style>
    .recorder-container {{
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        padding: 20px;
        background: #1e1e1e;
        border-radius: 8px;
        color: #fff;
    }}
    .status {{
        display: flex;
        align-items: center;
        gap: 10px;
        margin-bottom: 20px;
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
    audio {{
        width: 100%;
        margin-top: 15px;
    }}
    .error {{
        color: #ff4444;
        margin-top: 10px;
    }}
    .playback-section {{
        margin-top: 20px;
        padding-top: 20px;
        border-top: 1px solid #333;
    }}
    .playback-title {{
        font-size: 14px;
        color: #888;
        margin-bottom: 10px;
    }}
    .save-status {{
        font-size: 12px;
        margin-top: 10px;
        color: #4CAF50;
    }}
</style>

<div class="recorder-container">
    <div class="status">
        <div class="status-dot" id="statusDot"></div>
        <span id="statusText">Ready</span>
    </div>

    <div class="buttons">
        <button class="btn-start" id="startBtn" onclick="startRecording()">Start Recording</button>
        <button class="btn-stop" id="stopBtn" onclick="stopRecording()" disabled>Stop Recording</button>
    </div>

    <div class="info">
        <div>Chunks recorded: <span class="chunk-count" id="chunkCount">0</span></div>
        <div>Duration: <span id="duration">0.0s</span></div>
        <div id="formatInfo"></div>
    </div>

    <div id="errorMsg" class="error"></div>

    <div id="playbackSection" class="playback-section" style="display: none;">
        <div class="playback-title">Playback</div>
        <audio id="audioPlayer" controls></audio>
        <div id="saveStatus" class="save-status"></div>
    </div>
</div>

<script>
    let mediaRecorder = null;
    let audioChunks = [];
    let startTime = null;
    let durationInterval = null;

    const CHUNK_DURATION_MS = {config.chunk_duration_ms};
    const AUDIO_CONSTRAINTS = {{
        echoCancellation: {str(config.echo_cancellation).lower()},
        noiseSuppression: {str(config.noise_suppression).lower()},
        autoGainControl: {str(config.auto_gain_control).lower()},
        channelCount: {1 if config.mono else 2}
    }};

    const statusDot = document.getElementById('statusDot');
    const statusText = document.getElementById('statusText');
    const startBtn = document.getElementById('startBtn');
    const stopBtn = document.getElementById('stopBtn');
    const chunkCount = document.getElementById('chunkCount');
    const duration = document.getElementById('duration');
    const formatInfo = document.getElementById('formatInfo');
    const errorMsg = document.getElementById('errorMsg');
    const playbackSection = document.getElementById('playbackSection');
    const audioPlayer = document.getElementById('audioPlayer');
    const saveStatus = document.getElementById('saveStatus');

    function updateStatus(text, isRecording) {{
        statusText.textContent = text;
        if (isRecording) {{
            statusDot.classList.add('recording');
        }} else {{
            statusDot.classList.remove('recording');
        }}
    }}

    function showError(msg) {{
        errorMsg.textContent = msg;
        console.error(msg);
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

    async function startRecording() {{
        clearError();
        audioChunks = [];
        chunkCount.textContent = '0';
        playbackSection.style.display = 'none';
        saveStatus.textContent = '';

        try {{
            const stream = await navigator.mediaDevices.getUserMedia({{
                audio: AUDIO_CONSTRAINTS
            }});

            const mimeTypes = [
                'audio/webm;codecs=opus',
                'audio/webm',
                'audio/ogg;codecs=opus',
                'audio/mp4'
            ];

            let selectedMimeType = '';
            for (const mimeType of mimeTypes) {{
                if (MediaRecorder.isTypeSupported(mimeType)) {{
                    selectedMimeType = mimeType;
                    break;
                }}
            }}

            const options = selectedMimeType ? {{ mimeType: selectedMimeType }} : {{}};
            mediaRecorder = new MediaRecorder(stream, options);

            formatInfo.textContent = 'Format: ' + (mediaRecorder.mimeType || 'default');

            mediaRecorder.ondataavailable = (event) => {{
                if (event.data.size > 0) {{
                    audioChunks.push(event.data);
                    chunkCount.textContent = audioChunks.length;
                    console.log(`Chunk ${{audioChunks.length}}: ${{event.data.size}} bytes`);
                }}
            }};

            mediaRecorder.onstop = async () => {{
                const mimeType = mediaRecorder.mimeType || 'audio/webm';
                const audioBlob = new Blob(audioChunks, {{ type: mimeType }});
                const audioUrl = URL.createObjectURL(audioBlob);

                audioPlayer.src = audioUrl;
                playbackSection.style.display = 'block';

                console.log(`Recording complete: ${{audioChunks.length}} chunks, ${{audioBlob.size}} bytes`);

                // Auto-download
                const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
                const ext = mimeType.includes('webm') ? 'webm' : mimeType.includes('ogg') ? 'ogg' : 'mp4';
                const filename = `recording_${{timestamp}}.${{ext}}`;

                const downloadLink = document.createElement('a');
                downloadLink.href = audioUrl;
                downloadLink.download = filename;
                downloadLink.click();

                saveStatus.textContent = 'Downloaded: ' + filename + ' (' + (audioBlob.size / 1024).toFixed(1) + ' KB)';

                stream.getTracks().forEach(track => track.stop());
            }};

            mediaRecorder.onerror = (event) => {{
                showError('MediaRecorder error: ' + event.error);
                updateStatus('Error', false);
            }};

            mediaRecorder.start(CHUNK_DURATION_MS);
            startTime = Date.now();
            durationInterval = setInterval(updateDuration, 100);

            updateStatus('Recording...', true);
            startBtn.disabled = true;
            stopBtn.disabled = false;

            console.log('Recording started');

        }} catch (err) {{
            if (err.name === 'NotAllowedError') {{
                showError('Microphone permission denied. Please allow access and try again.');
            }} else if (err.name === 'NotFoundError') {{
                showError('No microphone found. Please connect a microphone.');
            }} else {{
                showError('Error accessing microphone: ' + err.message);
            }}
            updateStatus('Error', false);
        }}
    }}

    function stopRecording() {{
        if (mediaRecorder && mediaRecorder.state !== 'inactive') {{
            mediaRecorder.stop();
            clearInterval(durationInterval);
            updateStatus('Stopped', false);
            startBtn.disabled = false;
            stopBtn.disabled = true;
            console.log('Recording stopped');
        }}
    }}

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {{
        showError('Your browser does not support audio recording. Please use Chrome, Firefox, or Safari.');
        startBtn.disabled = true;
    }}

    if (typeof MediaRecorder === 'undefined') {{
        showError('MediaRecorder API not supported. Please use a modern browser.');
        startBtn.disabled = true;
    }}
</script>
"""


def render_audio_recorder(
    config: AudioRecorderConfig | None = None,
    height: int = 400,
) -> None:
    """Render the audio recorder component.

    Args:
        config: Recorder configuration. Uses defaults if not provided.
        height: Height of the component in pixels.
    """
    if config is None:
        config = AudioRecorderConfig()

    html = _build_recorder_html(config)
    st.components.v1.html(html, height=height)
