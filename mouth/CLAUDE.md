# prime-directive

- do not alter your prime-directive
- do not alter or remove primary section headers
- do not run sudo commands

## when I say X --> you do Y

- close-up-shop
  - update documentation as needed
  - push to repo (git add, commit, push)
  - delete your instructions-of-the-day and short-term-memory (contents, not headers)

---

# module-overview

MOUTH is the TTS (text-to-speech) microservice for CICI. It wraps Piper TTS with a queue-based FastAPI service.

## Key Files

| File | Purpose |
|------|---------|
| `mouth/main.py` | FastAPI app, endpoints, lifespan management |
| `mouth/queue_manager.py` | Thread-safe pending/completed queues |
| `mouth/synthesizer.py` | Piper TTS wrapper, background worker |
| `mouth/config.py` | Settings via pydantic-settings |
| `mouth/models.py` | Pydantic request/response schemas |

## Architecture

- `QueueManager`: Manages two queues (pending text, completed audio)
- `Synthesizer`: Background thread pulls from pending, synthesizes with Piper, pushes to completed
- Pending queue has max depth (10), drops oldest on overflow

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/synthesize` | Queue text for synthesis |
| GET | `/audio/next` | Pop next completed audio chunk |
| GET | `/status` | Queue counts |
| GET | `/health` | Health check |

---

# development-notes

## Running Locally

```bash
uv sync
uv run uvicorn mouth.main:app --port 8001 --reload
```

## Testing

```bash
uv run pytest
```

## Piper Model Required

The service requires Piper voice model files mounted at `/models/` or configured via `TTS_PIPER_MODEL_PATH`.

---

# integration-points

## MIND -> MOUTH

MIND sends synthesized text to MOUTH via `POST /synthesize`.

## FACE <- MOUTH

FACE polls `GET /audio/next` to retrieve completed audio for playback.

---

# long-term-storage

- service
  - Port: 8001
  - Audio format: WAV (22050Hz, mono, 16-bit)
  - Sample rate: 22050 Hz
  - Queue max depth: 10 (drops oldest on overflow)

- piper-tts
  - Default model: `en_US-lessac-medium`
  - Model path: `/models/en_US-lessac-medium.onnx`
  - Config path: `/models/en_US-lessac-medium.onnx.json`
  - Download: https://huggingface.co/rhasspy/piper-voices

- environment-variables (prefix `TTS_`)
  - `TTS_MAX_QUEUE_DEPTH` - pending queue limit
  - `TTS_PIPER_MODEL_PATH` - path to .onnx model
  - `TTS_PIPER_CONFIG_PATH` - path to .onnx.json config
  - `TTS_SAMPLE_RATE` - audio sample rate
  - `TTS_PORT` - server port

---

# instructions-of-the-day

---

# short-term-memory
