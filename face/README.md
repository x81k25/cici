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

## Backend Connection

FACE connects to the MIND REST API:

| Environment | URL |
|-------------|-----|
| Development | `http://localhost:8765` |
| Production (SSL) | `https://your-host:8765` |

Configuration via `.env`:
```bash
CICI_API_HOST=localhost
CICI_API_PORT=8765
CICI_API_SECURE=false
```

## Architecture

```
face/
├── app.py              # Main Streamlit application
├── mind_client.py      # HTTP client for MIND REST API
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
