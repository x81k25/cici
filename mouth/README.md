# MOUTH - Text-to-Speech Service

TTS microservice using Piper for the CICI voice assistant.

## Overview

MOUTH accepts text from MIND and synthesizes speech using Piper TTS. It uses a queue-based architecture to handle bursts of text while maintaining responsiveness.

## Architecture

```
POST /synthesize                GET /audio/next
      │                               │
      ▼                               │
┌─────────────────────┐               │
│  Pending Queue (10) │               │
│  [text][text][...]  │               │
└─────────┬───────────┘               │
          │                           │
          ▼                           │
┌─────────────────────┐               │
│  Background Worker  │               │
│  (Piper TTS)        │               │
└─────────┬───────────┘               │
          │                           │
          ▼                           │
┌─────────────────────┐               │
│  Completed Buffer   │◄──────────────┘
│  [wav][wav][...]    │
└─────────────────────┘
```

- **Pending Queue**: Max 10 items, drops oldest on overflow
- **Background Worker**: Sequential synthesis with Piper
- **Completed Buffer**: Holds WAV audio chunks for pickup

## API

### `POST /synthesize`

Queue text for synthesis.

**Request:**
```json
{
  "text": "Hello world",
  "request_id": "optional-trace-id"
}
```

**Response (202):**
```json
{
  "status": "queued",
  "request_id": "optional-trace-id",
  "queue_position": 1,
  "pending_count": 1
}
```

### `GET /audio/next`

Get next completed audio chunk.

**Response (200):** `audio/wav` binary data

**Response (204):** No audio available

**Headers:**
- `X-Pending-Count`: Items awaiting synthesis
- `X-Completed-Count`: Audio chunks ready
- `X-Request-Id`: Original request ID

### `GET /status`

```json
{
  "pending_count": 3,
  "completed_count": 1
}
```

### `GET /health`

```json
{
  "status": "healthy",
  "synthesizer_running": true
}
```

## Configuration

Environment variables (prefix `TTS_`):

| Variable | Default | Description |
|----------|---------|-------------|
| `TTS_MAX_QUEUE_DEPTH` | 10 | Max pending queue size |
| `TTS_PIPER_MODEL_PATH` | `/models/en_US-lessac-medium.onnx` | Piper model file |
| `TTS_PIPER_CONFIG_PATH` | `/models/en_US-lessac-medium.onnx.json` | Piper config file |
| `TTS_SAMPLE_RATE` | 22050 | Output audio sample rate |
| `TTS_PORT` | 8001 | Server port |

## Development

```bash
# Install dependencies
uv sync

# Run server
uv run uvicorn app.main:app --port 8001 --reload

# Run tests
uv run pytest
```

## Docker

```bash
# Build
docker build -t mouth .

# Run (mount Piper model)
docker run -p 8001:8001 -v /path/to/models:/models mouth
```

## Piper Models

Download models from [rhasspy/piper](https://github.com/rhasspy/piper/blob/master/VOICES.md).

Recommended: `en_US-lessac-medium` for quality/speed balance.

```bash
# Download model
curl -LO https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx
curl -LO https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json
```
