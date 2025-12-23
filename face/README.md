# FACE - Frontend UI

Streamlit-based frontend UI for the cici voice and text-based personal assistant.

## Overview

FACE provides a browser-based interface for interacting with MIND and EARS:
- Text input with voice-style syntax
- Audio streaming to EARS for transcription (via AudioWorklet)
- Session management (create, join, kill)
- Real-time command results display
- Mode switching (Ollama, CLI, Claude Code)

## Quick Start

```bash
# Install dependencies
uv sync

# Start the frontend (requires MIND server running)
uv run streamlit run app.py
```

The UI will be available at http://localhost:8501

## Configuration

FACE uses a two-tier configuration system:

**Root `.env`** (shared across services):
| Variable | Default | Description |
|----------|---------|-------------|
| `MIND_HOST` | `localhost` | MIND service host |
| `MIND_PORT` | `8765` | MIND service port |
| `EARS_HOST` | `localhost` | EARS service host |
| `EARS_PORT` | `8766` | EARS service port |
| `MOUTH_HOST` | `localhost` | MOUTH service host |
| `MOUTH_PORT` | `8001` | MOUTH service port |
| `SAMPLE_RATE` | `16000` | Audio sample rate (Hz) |
| `LOG_LEVEL` | `INFO` | Logging level |

**Browser-Accessible URLs** (for non-localhost deployments):
| Variable | Description |
|----------|-------------|
| `CICI_EARS_WS_URL` | Override EARS WebSocket URL (e.g., `ws://your-host:8766`) |
| `CICI_MOUTH_URL` | Override MOUTH HTTP URL (e.g., `http://your-host:8001`) |

**Module `config/config.yaml`** (FACE-specific tuning):
```yaml
audio:
  chunk_duration_ms: 100     # Audio chunk size for streaming
  echo_cancellation: true
  noise_suppression: true
  auto_gain_control: true

webrtc:
  ice_servers:
    - "stun:stun.l.google.com:19302"

timeouts:
  connect: 5.0               # General connection timeout
  llm_request: 120.0         # LLM request timeout (can be slow)
  health_check: 2.0

ui:
  max_log_messages: 50
  audio_refresh_interval: 1.0
```

## Architecture

```
face/
├── app.py              # Main Streamlit application
├── mind_client.py      # HTTP client for MIND REST API
├── mouth_client.py     # HTTP client for MOUTH TTS service
├── utils/
│   ├── audio_streamer.py  # AudioWorklet-based streaming to EARS
│   └── audio_recorder.py  # Local recording component
├── pages/
│   └── testing.py      # Audio testing benchmarks
├── .env                # Configuration
└── pyproject.toml      # Dependencies
```

## Audio Streaming

FACE streams audio to EARS using the Web Audio API's AudioWorklet:

**Audio Format (sent to EARS)**:
- Raw PCM Int16 (no container)
- 16000 Hz sample rate
- Mono (1 channel)

The testing page (`pages/testing.py`) provides benchmarks for:
1. **Local Recording** - Record and playback locally
2. **WebSocket Streaming** - Stream to EARS and view transcriptions

## TTS Audio Playback

In audio mode, FACE polls MOUTH for synthesized speech and plays it automatically:

- Polls `GET /audio/next` during audio streaming
- Plays WAV audio via `st.audio()` with autoplay
- Only active when in audio mode (not text mode)

**Note:** Browser autoplay requires user interaction first (clicking "START" enables it).

## Usage

### Connection

1. The app auto-connects on startup
2. Session status shows in the sidebar
3. Use **Disconnect** / **Connect** to manage connection

### Session Management

In the sidebar:
- View active sessions with idle time
- **Join** other sessions
- **Kill** individual or all sessions
- **Refresh** to update session list

### Modes

Switch modes by typing triggers:

| Trigger | Mode |
|---------|------|
| `chat mode`, `back to chat` | Ollama (conversation) |
| `commands mode`, `cli mode` | CLI (shell commands) |
| `let's code`, `code mode` | Claude Code (coding) |

### Voice-Style Syntax

Type commands using natural speech patterns:

| Say | Get |
|-----|-----|
| minus | `-` |
| slash | `/` |
| dot | `.` |
| pipe | `\|` |
| greater than | `>` |
| tilde | `~` |

**Examples:**
- `ls minus la` → `ls -la`
- `cat slash etc slash hosts` → `cat /etc/hosts`

## Running Tests

```bash
# Install dev dependencies
uv sync --extra dev

# Unit tests (fast, no services needed)
uv run pytest tests/test_audio_apptest.py -v

# Playwright E2E tests (requires FACE + EARS running)
uv run pytest tests/test_audio_chat.py -v
```

### Test Files

| File | Type | Description |
|------|------|-------------|
| `test_audio_apptest.py` | Unit | Audio config, processor, constants (16 tests) |
| `test_audio_chat.py` | E2E | Playwright browser tests with Firefox |

### Integration Tests

FACE → EARS integration tests are in the root `/tests/` directory:
```bash
cd /infra/experiments/cici
uv run pytest tests/test_face_ears_integration.py -v
```

## Stopping the Frontend

```bash
# If running in foreground, press Ctrl+C

# Or kill by port
pkill -f "streamlit run"
```
