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

### FACE → MIND

FACE communicates with MIND via REST API:

```bash
# Create session
POST /sessions → {session_id, mode, ...}

# Process text
POST /sessions/{id}/process → {input, llm_response, cli_result, ...}

# List sessions
GET /sessions → [{session_id, mode, idle_seconds}, ...]
```

### FACE → EARS (future)

When voice input is added, FACE will stream audio to EARS:

```
FACE ──WebSocket──▶ EARS ──transcription──▶ FACE ──text──▶ MIND
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

All images are published to: `ghcr.io/x81k25/cici-<service>`

| Service | Image URL |
|---------|-----------|
| **MIND** | `ghcr.io/x81k25/cici-mind` |
| **EARS** | `ghcr.io/x81k25/cici-ears` |
| **MOUTH** | `ghcr.io/x81k25/cici-mouth` |
| **FACE** | `ghcr.io/x81k25/cici-face` |

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
docker pull ghcr.io/x81k25/cici-mind:dev
docker pull ghcr.io/x81k25/cici-ears:dev
docker pull ghcr.io/x81k25/cici-mouth:dev
docker pull ghcr.io/x81k25/cici-face:dev

# Pull stable versions
docker pull ghcr.io/x81k25/cici-mind:latest
docker pull ghcr.io/x81k25/cici-ears:latest
docker pull ghcr.io/x81k25/cici-mouth:latest
docker pull ghcr.io/x81k25/cici-face:latest
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
