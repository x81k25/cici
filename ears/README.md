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
```

## WebSocket Protocol

**Endpoint**: `ws://localhost:8766/`

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
│   └── vad_processor.py        # Voice Activity Detection
└── utils.py             # Audio utilities
```
