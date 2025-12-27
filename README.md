# cici - Voice and Text Personal Assistant

A microservices-based personal assistant with voice transcription, command routing, and a web UI.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                           FACE                                  │
│                    (Streamlit Frontend)                         │
│                     http://localhost:8501                       │
└─────────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              │ HTTP REST                     │ WebSocket
              ▼                               ▼
┌─────────────────────────────┐   ┌─────────────────────────────┐
│           MIND              │   │           EARS              │
│   (Logic & Routing API)     │   │   (Transcription Service)   │
│   http://localhost:8765     │   │   ws://localhost:8766       │
├─────────────────────────────┤   ├─────────────────────────────┤
│ • Session management        │   │ • Audio streaming           │
│ • Voice-to-CLI translation  │   │ • Voice Activity Detection  │
│ • Command routing           │   │ • Whisper transcription     │
│ • Mode switching            │   │ • Raw text output           │
│ • Ollama/Claude/CLI exec    │   │                             │
└─────────────────────────────┘   └─────────────────────────────┘
```

## Components

| Component | Description | Port | Protocol |
|-----------|-------------|------|----------|
| **MIND** | Logic and routing service | 8765 | HTTP REST |
| **EARS** | Audio transcription service | 8766 | WebSocket |
| **MOUTH** | Text-to-speech service | 8001 | HTTP REST |
| **FACE** | Streamlit frontend UI | 8501 | HTTP |

### MIND - Logic & Routing

FastAPI service that handles:
- Session management (create, list, kill)
- Voice-to-CLI text translation
- Command routing (Ollama, CLI, Claude, Claude Code modes)
- Controller execution

See [`mind/README.md`](mind/README.md) for details.

### EARS - Transcription

WebSocket service for pure audio transcription:
- Streaming audio via WebSocket
- Voice Activity Detection (VAD)
- Whisper-based speech-to-text
- Raw transcription output (no business logic)

See [`ears/README.md`](ears/README.md) for details.

### FACE - Frontend

Streamlit-based web UI:
- Text input with voice-style syntax
- Session management
- Mode switching
- Command result display

See [`face/README.md`](face/README.md) for details.

### MOUTH - Text-to-Speech

FastAPI service for TTS synthesis:
- Piper TTS integration
- Queue-based audio generation
- WAV audio output (22050Hz)

See [`mouth/README.md`](mouth/README.md) for details.

## Quick Start

### 1. Start MIND (required)

```bash
cd mind
uv sync
uv run python -m mind.main
```

### 2. Start EARS (optional, for voice)

```bash
cd ears
uv sync
uv run python -m ears.main
```

### 3. Start FACE (frontend)

```bash
cd face
uv sync
uv run streamlit run app.py
```

Open http://localhost:8501 in your browser.

## Inter-Service Communication

### Data Flow Overview

```
┌──────────────────────────────────────────────────────────────────────────┐
│                              USER                                         │
└──────────────────────────────────────────────────────────────────────────┘
                    │ text input              │ voice input
                    ▼                         ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                              FACE                                         │
│                        (Streamlit Frontend)                               │
│  • Sends text to MIND        • Streams audio to EARS                     │
│  • Polls MOUTH for audio     • Receives transcriptions from EARS         │
│  • Plays audio to user       • Displays responses                        │
└──────────────────────────────────────────────────────────────────────────┘
         │                           │                        ▲
         │ HTTP REST                 │ WebSocket              │ HTTP REST
         ▼                           ▼                        │ (polling)
┌─────────────────────┐   ┌─────────────────────┐   ┌─────────────────────┐
│        MIND         │   │        EARS         │   │       MOUTH         │
│  (Logic & Routing)  │   │   (Transcription)   │   │   (Text-to-Speech)  │
│                     │   │                     │   │                     │
│  POST /process ─────┼───┼─────────────────────┼──►│  POST /synthesize   │
│                     │   │                     │   │                     │
└─────────────────────┘   └─────────────────────┘   └─────────────────────┘
```

### FACE → MIND (HTTP REST)

Session and text processing via REST API.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/sessions` | POST | Create new session |
| `/sessions` | GET | List all sessions |
| `/sessions/{id}` | GET | Get session details |
| `/sessions/{id}` | DELETE | Kill session |
| `/sessions/{id}/process` | POST | Process text input |
| `/sessions/{id}/cancel` | POST | Cancel running tasks |
| `/health` | GET | Health check |

**Create Session:**
```bash
POST /sessions
Content-Type: application/json

{"mode": "ollama"}  # optional, defaults to ollama

Response: {"session_id": "abc123", "mode": "ollama", "created_at": "..."}
```

**Process Text:**
```bash
POST /sessions/{id}/process
Content-Type: application/json

{"text": "what time is it"}

Response: {
  "input": "what time is it",
  "llm_response": "The current time is...",
  "cli_result": null,
  "mode": "ollama"
}
```

### FACE → EARS (WebSocket)

Real-time audio streaming for voice input.

**Connection:**
```
ws://localhost:8766/           # Standard mode
ws://localhost:8766/?debug=true  # Debug mode (includes audio analysis)
```

**Protocol:**
```
FACE ──[binary PCM audio]──► EARS
     16kHz, mono, int16

EARS ──[JSON messages]──► FACE
     {"type": "transcription", "text": "hello world", "final": true}
     {"type": "debug", "chunk_index": 1, "defects": [...], "metrics": {...}}
```

**Audio Format Requirements:**
- Sample rate: 16000 Hz
- Channels: 1 (mono)
- Format: int16 (signed 16-bit)
- Endianness: little-endian

**Debug Mode Defects:** `silence`, `low_volume`, `clipping`, `dc_offset`, `wrong_byte_order`, `wrong_sample_rate`, `truncated`, `noise_only`

### MIND → MOUTH (HTTP REST)

Text-to-speech synthesis requests from MIND.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/synthesize` | POST | Queue text for TTS |
| `/audio/next` | GET | Get next completed audio chunk |
| `/status` | GET | Queue status |
| `/health` | GET | Health check |

**Queue Text:**
```bash
POST /synthesize
Content-Type: application/json

{"text": "Hello, how can I help you?", "request_id": "req-123"}

Response: {"status": "queued", "request_id": "req-123"}
```

### FACE ← MOUTH (HTTP REST Polling)

FACE polls MOUTH for completed audio chunks.

**Get Audio:**
```bash
GET /audio/next

Response (audio ready):
  Status: 200
  Content-Type: audio/wav
  X-Pending-Count: 2
  X-Completed-Count: 1
  X-Request-Id: req-123
  Body: [WAV audio data]

Response (queue empty):
  Status: 204 No Content
```

### Complete Voice Interaction Flow

```
1. User speaks into microphone
   └─► FACE captures audio

2. FACE streams audio to EARS
   └─► WebSocket: binary PCM chunks

3. EARS transcribes and returns text
   └─► {"type": "transcription", "text": "turn on the lights", "final": true}

4. FACE sends transcription to MIND
   └─► POST /sessions/{id}/process {"text": "turn on the lights"}

5. MIND processes and responds
   └─► {"llm_response": "I'll turn on the lights for you", ...}

6. MIND queues TTS with MOUTH
   └─► POST /synthesize {"text": "I'll turn on the lights for you"}

7. FACE polls MOUTH for audio
   └─► GET /audio/next → 200 + WAV data

8. FACE plays audio to user
   └─► Browser audio playback
```

## Interaction Modes

All modes are managed by MIND:

| Mode | Trigger | Description |
|------|---------|-------------|
| **Ollama** | `chat mode`, `back to chat` | Conversational LLM (default) |
| **CLI** | `commands mode`, `cli mode` | Shell command execution |
| **Claude Code** | `let's code`, `code mode` | Coding assistant via SDK |

## External Services

| Service | Purpose | URL |
|---------|---------|-----|
| Ollama | LLM inference | `http://192.168.50.2:31435` |
| Anthropic API | Claude queries | `https://api.anthropic.com` |

## Docker Images

Pre-built Docker images are available from GitHub Container Registry (GHCR).

### Container Registry

All images are published to: `ghcr.io/x81k25/cici/<service>`

| Service | Image URL |
|---------|-----------|
| **MIND** | `ghcr.io/x81k25/cici/mind` |
| **EARS** | `ghcr.io/x81k25/cici/ears` |
| **MOUTH** | `ghcr.io/x81k25/cici/mouth` |
| **FACE** | `ghcr.io/x81k25/cici/face` |

### Image Tags

Images are tagged based on the git branch and event:

| Tag | Description | When Updated |
|-----|-------------|--------------|
| `dev` | Development branch | Push to `dev` branch |
| `main` | Production branch | Push to `main` branch |
| `latest` | Alias for `main` | Push to `main` branch |
| `sha-<commit>` | Specific commit | Every push |
| `pr-<number>` | Pull request build | PR to `main` |

**Note:** Both `dev` and `main` tags are always available. Use `dev` for testing latest changes, `main`/`latest` for stable releases.

### Pulling Images

```bash
# Pull dev versions
docker pull ghcr.io/x81k25/cici/mind:dev
docker pull ghcr.io/x81k25/cici/ears:dev
docker pull ghcr.io/x81k25/cici/mouth:dev
docker pull ghcr.io/x81k25/cici/face:dev

# Pull stable versions
docker pull ghcr.io/x81k25/cici/mind:latest
docker pull ghcr.io/x81k25/cici/ears:latest
docker pull ghcr.io/x81k25/cici/mouth:latest
docker pull ghcr.io/x81k25/cici/face:latest
```

### Running with Docker Compose

```bash
# Start all services
docker compose up -d

# Check status
docker compose ps

# View logs
docker compose logs -f

# Stop all services
docker compose down
```

## Development

### Running Tests

```bash
# MIND tests
cd mind && uv run pytest tests/ -v

# EARS tests
cd ears && uv run pytest tests/ -v

# FACE tests (if any)
cd face && uv run pytest tests/ -v
```

### Project Structure

```
cici/
├── mind/                      # Logic & routing service
├── ears/                      # Transcription service
├── mouth/                     # Text-to-speech service
├── face/                      # Frontend UI
├── tests/                     # Integration tests
├── .env.example               # Configuration template
├── docker-compose.yml         # Container orchestration
└── README.md                  # This file
```
