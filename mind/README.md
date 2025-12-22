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

# Kill foreground process
Ctrl+C

# Kill background process (by name)
pkill -f "mind.main"

# Kill background process (by port)
lsof -ti :8765 | xargs kill
```

## REST API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/transcript` | Buffer partial transcription from EARS (1+ words), process on "execute" |
| POST | `/text` | Process complete text input from FACE |
| GET | `/messages` | Poll for response messages (FACE) |
| GET | `/health` | Health check |

## EARS → MIND Protocol

EARS sends partial transcriptions to MIND as speech is recognized:

```bash
# Send partial transcription (1+ words)
curl -X POST http://localhost:8765/transcript \
  -H "Content-Type: application/json" \
  -d '{"text": "list files"}'
# Response: {"status": "buffered", "buffer": ["list", "files"], "command": null}

# When user says "execute", command is processed
curl -X POST http://localhost:8765/transcript \
  -H "Content-Type: application/json" \
  -d '{"text": "execute"}'
# Response: {"status": "processing", "command": "list files", "buffer": null}

# Poll for results
curl http://localhost:8765/messages
```

## FACE → MIND Protocol

FACE sends complete text (typed input):

```bash
# Process complete text
curl -X POST http://localhost:8765/text \
  -H "Content-Type: application/json" \
  -d '{"text": "list files in current directory"}'
# Response: {"status": "ok"}

# Poll for results
curl http://localhost:8765/messages
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
