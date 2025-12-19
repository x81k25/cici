# MIND - Logic and Routing Service

FastAPI service for command processing, session management, and controller execution.

## Overview

MIND is the brain of the cici system. It handles:
- Session management (create, list, kill sessions)
- Voice-to-CLI translation
- Command routing (Ollama, CLI, Claude, Claude Code modes)
- TTS output generation

## Quick Start

```bash
# Install dependencies
uv sync

# Run the server
uv run uvicorn mind.main:app --reload --port 8765

# Or use the CLI
uv run python -m mind.main
```

## REST API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/sessions` | Create new session |
| GET | `/sessions` | List all sessions |
| GET | `/sessions/{id}` | Get session state |
| DELETE | `/sessions/{id}` | Kill session |
| POST | `/sessions/{id}/process` | Process text input |
| POST | `/sessions/{id}/cancel` | Cancel active tasks |

## Example Usage

```bash
# Create a session
curl -X POST http://localhost:8765/sessions

# Process text
curl -X POST http://localhost:8765/sessions/{session_id}/process \
  -H "Content-Type: application/json" \
  -d '{"text": "list files in current directory"}'

# List sessions
curl http://localhost:8765/sessions
```

## Running Tests

```bash
# All tests
uv run pytest tests/ -v

# With coverage
uv run pytest tests/ -v --cov=mind
```

## Interaction Modes

MIND supports three interaction modes:

| Mode | Trigger | Description |
|------|---------|-------------|
| **Ollama** | `chat mode`, `back to chat` | Conversational LLM (default) |
| **CLI** | `commands mode`, `cli mode` | Shell command execution |
| **Claude Code** | `let's code`, `code mode` | Coding assistant via SDK |

See [`docs/modes.md`](docs/modes.md) for detailed mode diagrams.

## Architecture

```
mind/
├── main.py              # FastAPI server
├── session.py           # Session management
├── input_processor.py   # Text processing (no audio)
├── command_router.py    # Command routing logic
├── schemas.py           # Pydantic schemas
├── controllers/
│   ├── cli.py           # CLI command execution
│   ├── claude.py        # Claude API (stateless)
│   ├── claude_code.py   # Claude Agent SDK (stateful)
│   └── ollama.py        # Ollama LLM
└── core/
    ├── commands.py      # Command trigger detection
    ├── prompts.py       # System prompt loading
    ├── translation.py   # Voice-to-CLI translation
    ├── session_logger.py # Logging
    ├── tmux_session.py  # Tmux management
    └── tts.py           # Text-to-speech
```
