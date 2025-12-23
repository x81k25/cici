# EARS - Pure Transcription Service

WebSocket service for audio transcription. Audio in, text out.

## Overview

EARS is a standalone transcription service that:
- Receives streaming audio via WebSocket
- Uses Voice Activity Detection (VAD) to detect speech
- Transcribes audio to text via Whisper
- Returns raw transcriptions (no command routing or business logic)

## Quick Start

```bash
# Install dependencies
uv sync

# Run the server
uv run python -m ears.main

# Run with debug logging
uv run python -m ears.main --debug

# Stop the server (foreground)
Ctrl+C

# Stop the server (background)
pkill -f "ears.main"

# Kill background process (by port)
lsof -ti :8766 | xargs kill
# or
fuser -k 8766/tcp
```

## WebSocket Protocol

**Endpoint**: `ws://localhost:8766/`

**Query Parameters**:
| Parameter | Default | Description |
|-----------|---------|-------------|
| `debug` | `false` | Enable audio diagnostics. Adds ~0.1ms latency per chunk (<1% overhead). |

Example: `ws://localhost:8766/?debug=true`

**Audio Format (required)**:
- Raw PCM (no container)
- Int16 samples (16-bit signed little-endian)
- 16000 Hz sample rate
- Mono (1 channel)

**Client → Server**: Binary PCM audio chunks

**Server → Client** (JSON):
```json
{"type": "listening", "sample_rate": 16000}
{"type": "transcription", "text": "hello world", "final": true}
{"type": "error", "message": "..."}
{"type": "closed", "reason": "..."}
```

**Debug Mode Messages** (when `?debug=true`):
```json
{
  "type": "debug",
  "chunk_index": 1,
  "sample_count": 1600,
  "duration_ms": 100.0,
  "defects": [
    {"code": "low_volume", "severity": "warning", "message": "...", "value": 0.005, "threshold": 0.01}
  ],
  "metrics": {
    "rms": 0.15,
    "peak": 0.45,
    "dc_offset": 0.001,
    "clipping_ratio": 0.0,
    "zero_crossing_rate": 0.12,
    "spectral_centroid": 1250.5
  }
}
```

## Debug Mode Defects

Debug mode analyzes each audio chunk for potential issues:

| Defect | Severity | Description |
|--------|----------|-------------|
| `silence` | error | Audio is silent (RMS < 0.0001) |
| `low_volume` | warning | Very quiet audio (RMS < 0.01) |
| `noise_only` | warning | Random noise, no speech pattern (ZCR > 0.4) |
| `clipping` | error | Audio distortion (>2% samples at max) |
| `dc_offset` | warning | DC bias in signal (mean > 0.1) |
| `wrong_byte_order` | error | Byte endianness mismatch |
| `wrong_sample_rate` | warning | Spectral centroid outside 800-4000 Hz |
| `wrong_chunk_size` | warning | Chunk duration outside 50-500ms |
| `truncated` | warning | Stream ended during active speech (detected at stream close) |
| `empty_chunk` | error | Zero-length audio received |

**Performance**: Debug analysis adds ~0.1ms per chunk. Safe for production use.

## Configuration

EARS uses a two-tier configuration system:

**Root `.env`** (shared across services):
| Variable | Default | Description |
|----------|---------|-------------|
| `EARS_HOST` | `localhost` | Host to bind to |
| `EARS_PORT` | `8766` | Port to bind to |
| `MIND_HOST` | `localhost` | MIND service host |
| `MIND_PORT` | `8765` | MIND service port |
| `SAMPLE_RATE` | `16000` | Audio sample rate (Hz) |
| `EARS_SILENCE_DURATION_MS` | `1000` | Silence duration to trigger transcription |
| `LOG_LEVEL` | `INFO` | Logging level |

**Module `ears/config/config.yaml`** (EARS-specific tuning):
```yaml
vad:
  speech_threshold: 0.5       # VAD probability threshold
  min_speech_duration_ms: 250 # Minimum speech to process
  speech_pad_ms: 100          # Padding around speech
  max_buffer_seconds: 30.0    # Max buffer before flush

whisper:
  model_size: "small"         # tiny, base, small, medium, large-v3
  device: "cpu"               # cpu or cuda
  compute_type: "int8"        # int8 (CPU) or float16 (GPU)
  language: "en"
  beam_size: 5

websocket:
  ping_interval: 30
  ping_timeout: 120

hallucination_phrases:        # Phrases to filter out
  - "thank you"
  - "thanks for watching"
```

## EARS → MIND Integration

EARS automatically forwards each transcription to MIND's `/transcript` endpoint for buffering and command processing.

**Flow:**
```
User speaks: "list files execute"
    ↓
EARS transcribes: "list files"  →  POST /transcript {"text": "list files"}
    ↓                                    → {"status": "buffered", "buffer": ["list", "files"]}
EARS transcribes: "execute"     →  POST /transcript {"text": "execute"}
    ↓                                    → {"status": "processing", "command": "list files"}
MIND processes command
```

**MIND Responses:**
- `{"status": "buffered", "buffer": [...], "command": null}` - Text added to buffer
- `{"status": "processing", "command": "...", "buffer": null}` - "execute" triggered command processing

The integration is fire-and-forget; EARS continues functioning even if MIND is unavailable.

## Running Tests

```bash
# All tests
uv run pytest tests/ -v

# Skip slow tests (model loading)
uv run pytest tests/ -v -m "not slow"
```

## Architecture

```
ears/
├── main.py              # WebSocket server
├── schemas.py           # Pydantic message schemas
├── audio/
│   ├── whisper_client.py       # Standard Whisper
│   ├── faster_whisper_client.py # Optimized Whisper
│   ├── vad_processor.py        # Voice Activity Detection
│   └── audio_analyzer.py       # Debug mode audio analysis
└── utils.py             # Audio utilities
```
