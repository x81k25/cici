# Client-Side Audio Capture - Streamlit Application

## Tech Stack
- **Streamlit** (Python web framework)
- **Custom HTML component** via `st.components.v1.html()`
- **MediaRecorder API** (browser audio capture)
- **WebSocket** (Python `websockets` package for Benchmark 2+)

---

## BENCHMARK 1: Local Recording & Playback

### Goal
Verify browser audio capture and playback work correctly

### Requirements
1. Streamlit app with embedded HTML/JS component
2. "Start Recording" button → begins MediaRecorder
3. "Stop Recording" button → stops MediaRecorder
4. MediaRecorder configured:
   - 500ms chunks (`timeslice=500`)
   - WebM/Opus format (browser default)
   - Mono audio preferred
   - Enable `echoCancellation`, `noiseSuppression`, `autoGainControl` constraints
5. Store chunks in JavaScript array during recording
6. On stop: Combine chunks into single Blob
7. Display audio player element to playback recorded audio
8. Show recording status indicator (recording/stopped)

### Testing
- Record 10 seconds of speech
- Play back recording - should sound clear
- Check browser console for any errors
- Verify chunks are being created every 500ms

### Files to Create
- `app.py` (main Streamlit app)
- Audio component can be inline HTML in `st.components.v1.html()`

---

## BENCHMARK 2: WebSocket Transmission

### Goal
Send audio chunks to server in real-time

### Requirements
1. **Keep everything from Benchmark 1**
2. Add WebSocket connection to server
   - Connection URL: `ws://localhost:8765` (configurable)
   - Connect when "Start Recording" clicked
   - Disconnect when "Stop Recording" clicked
3. Send each MediaRecorder chunk immediately via WebSocket as it's available
   - Send as binary blob (not base64)
4. Add connection status indicator (connected/disconnected/error)
5. Basic error handling:
   - Log WebSocket errors to console
   - Show error message in UI if connection fails
6. **Keep local playback from Benchmark 1** for testing

### Testing
- Start recording, verify chunks arrive at server
- Stop recording, verify clean disconnection
- Test with server offline (should show error)
- Compare local playback vs server-received audio

### Server Test Script Needed
Simple Python WebSocket server that:
- Accepts connections on `ws://localhost:8765`
- Receives binary chunks
- Saves chunks to files for testing
- Logs chunk size and timing

---

## BENCHMARK 3: Full Streaming Support

### Goal
Continuous, infinite-duration streaming with proper connection handling

### Requirements
1. **Keep everything from Benchmark 2**
2. Remove "Stop Recording" button (or make optional)
3. Recording continues indefinitely once started
4. WebSocket auto-reconnection logic:
   - Detect disconnection (close event)
   - Attempt reconnect with exponential backoff (1s, 2s, 4s, 8s, max 30s)
   - Show reconnection status in UI ("Reconnecting in 3s...")
   - Keep MediaRecorder running during reconnection attempts
5. Client-side chunk buffering during disconnection:
   - Queue chunks in memory when WebSocket closed
   - Set max buffer size (e.g., 60 chunks = 30 seconds)
   - Send queued chunks in order when reconnected
   - Show buffer status ("Buffered: 15 chunks")
6. Handle buffer overflow:
   - **Pause MediaRecorder** when buffer reaches max size
   - Display clear message: "Buffer full - recording paused. Reconnecting..."
   - **Resume MediaRecorder** automatically when buffer empties (chunks sent)
   - No audio data is lost - recording pauses instead

### Testing
- Start streaming, let run for 5+ minutes
- Simulate network issues:
  - Stop server mid-stream
  - Restart server, verify reconnection
  - Verify queued chunks are sent
- Test buffer overflow (disconnect for 60+ seconds)
- Monitor memory usage during long sessions

---

## BENCHMARK 4: Production Features

### Goal
Add remaining production-ready features

### Requirements
1. **Keep everything from Benchmark 3**
2. Voice Activity Detection (VAD):
   - Use Web Audio API volume detection (simple threshold-based)
   - Monitor audio level in real-time
   - Only send chunks when volume > threshold
   - Add "silence detected" timeout (e.g., stop sending after 2s silence)
   - Show VAD status indicator (speaking/silent)
   - Make VAD toggle-able (on/off switch)
3. Session Management:
   - Generate unique session ID on start
   - Send session ID with first WebSocket message
   - Include session ID in all subsequent chunks
   - Add session reset button
4. Audio Constraints UI:
   - Settings panel for audio configuration:
     - Echo cancellation (on/off)
     - Noise suppression (on/off)
     - Auto gain control (on/off)
   - Apply settings before starting recording
5. Enhanced Error Handling:
   - Microphone permission denied → clear error message
   - MediaRecorder not supported → show browser compatibility message
   - WebSocket connection failed → suggest checking server status
   - Show error notifications in UI (not just console)
6. UI Polish:
   - Visual recording indicator (animated dot/pulse)
   - Audio level meter (real-time visualization)
   - Connection quality indicator (good/fair/poor based on latency)
   - Chunk send rate display ("Sending: 2 chunks/sec")

### Testing
- Test VAD with different noise levels
- Verify session IDs are consistent across reconnects
- Test all audio constraint combinations
- Test error scenarios with good UX
- Long session test (30+ minutes)
- Mobile browser testing (if applicable)

---

## Configuration Parameters

### Audio Settings
```python
CHUNK_DURATION_MS = 500  # MediaRecorder timeslice
AUDIO_CONSTRAINTS = {
    "echoCancellation": True,
    "noiseSuppression": True,
    "autoGainControl": True
}
```

### WebSocket Settings
```python
WEBSOCKET_URL = "ws://localhost:8765"
RECONNECT_INTERVALS = [1, 2, 4, 8, 16, 30]  # seconds
MAX_RECONNECT_ATTEMPTS = None  # infinite
```

### Buffering Settings
```python
MAX_BUFFER_CHUNKS = 60  # 30 seconds at 500ms/chunk
BUFFER_OVERFLOW_ACTION = "pause_recording"  # pause until buffer empties
```

### VAD Settings (Benchmark 4)
```python
VAD_ENABLED = False  # default off
VAD_THRESHOLD = 0.01  # volume threshold (0.0 to 1.0)
VAD_SILENCE_TIMEOUT_MS = 2000  # stop sending after 2s silence
```

---

## Implementation Notes

### Assumptions
- Server WebSocket endpoint is available at `ws://localhost:8765`
- Server handles binary WebM/Opus chunks
- Browser supports MediaRecorder API (Chrome 47+, Firefox 25+, Safari 14+)
- Mobile use case is primary - design for cellular networks

### Dependencies
```
streamlit>=1.28.0
# No additional Python packages needed for client side
```

### File Structure
```
project/
├── app.py                 # Main Streamlit application
├── requirements.txt       # Python dependencies
└── README.md             # Setup and testing instructions
```

### Testing Strategy
- Test each benchmark before moving to next
- Use browser DevTools Network tab to verify chunk transmission
- Monitor WebSocket connection state
- Test on multiple browsers (Chrome, Firefox, Safari)
- Test mobile browsers if applicable
- Simulate poor network conditions (Chrome DevTools throttling)

---

## Known Limitations

1. **MediaRecorder format**: Browser-dependent (usually WebM/Opus)
   - Server must handle decoding
   - No control over exact codec
   
2. **Client-side buffering**: Limited by browser memory
   - Recording automatically pauses when buffer full
   - No audio loss - just recording interruption during long outages
   - Acceptable for streaming use case
   
3. **VAD simplicity**: Volume-based detection not perfect
   - May trigger on loud non-speech sounds
   - May miss quiet speech
   - Good enough for primary use case
   
4. **No encryption**: WebSocket not using TLS
   - Use `wss://` in production
   - Add to configuration for Benchmark 4