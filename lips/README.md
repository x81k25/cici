# LIPS - Frontend UI

Streamlit-based frontend UI for the cici voice and text-based personal assistant.

## Overview

LIPS provides a browser-based interface for interacting with the MIND REST API:
- Text input with voice-style syntax
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

LIPS connects to the MIND REST API:

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
lips/
├── app.py           # Main Streamlit application
├── mind_client.py   # HTTP client for MIND REST API
├── .env             # Configuration
└── pyproject.toml   # Dependencies
```

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
uv run pytest tests/ -v
```

## Stopping the Frontend

```bash
# If running in foreground, press Ctrl+C

# Or kill by port
pkill -f "streamlit run"
```
