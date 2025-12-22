# TTS Service Implementation Plan

## 1. Project Structure

```
tts-service/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app + endpoints
│   ├── config.py            # Settings (queue depth, model path, etc.)
│   ├── queue_manager.py     # FIFO queue with drop-oldest logic
│   ├── synthesizer.py       # Piper TTS wrapper
│   └── models.py            # Pydantic request/response schemas
├── Dockerfile
├── requirements.txt
└── README.md
```

---

## 2. Components

| Component | Responsibility |
|-----------|----------------|
| **QueueManager** | Thread-safe FIFO queue (max 10); drops oldest on overflow; tracks pending vs completed |
| **Synthesizer** | Wraps Piper; runs in background thread; pulls from queue, pushes to completed buffer |
| **CompletedAudioBuffer** | Holds synthesized audio chunks in order; `pop()` returns next or `None` |
| **FastAPI App** | Exposes `/synthesize` and `/audio/next` |

---

## 3. Endpoints

### `POST /synthesize`

Accepts text from primary service for synthesis.

**Request Body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `text` | string | Yes | Sentence to synthesize |
| `request_id` | string | No | For tracing/logging |

**Responses:**

| Status | Meaning |
|--------|---------|
| `202 Accepted` | Text queued for synthesis |
| `400 Bad Request` | Invalid/empty text |

---

### `GET /audio/next`

Returns the next completed audio chunk.

**Responses:**

| Status | Body | Meaning |
|--------|------|---------|
| `200 OK` | `audio/wav` bytes | Audio ready |
| `204 No Content` | Empty | No audio available |

**Response Headers:**

| Header | Description |
|--------|-------------|
| `X-Pending-Count` | Number of sentences awaiting synthesis |
| `X-Completed-Count` | Number of audio chunks ready for pickup |

---

## 4. Processing Flow

```
┌──────────────────────────────────────────────────────────────────┐
│                         TTS Service                              │
│                                                                  │
│  POST /synthesize                                                │
│        │                                                         │
│        ▼                                                         │
│  ┌───────────────────────────────────────┐                       │
│  │        Pending Queue (max 10)         │                       │
│  │  [s10][s9][s8][s7][s6][s5][s4][s3][s2][s1]                   │
│  │        ▲                                                      │
│  │        │ (drops oldest if full)                               │
│  └────────┼──────────────────────────────┘                       │
│           │                                                      │
│           ▼                                                      │
│  ┌─────────────────┐                                             │
│  │ Background      │                                             │
│  │ Synthesizer     │ ◄── Piper TTS                               │
│  │ (sequential)    │                                             │
│  └────────┬────────┘                                             │
│           │                                                      │
│           ▼                                                      │
│  ┌───────────────────────────────────────┐                       │
│  │      Completed Audio Buffer           │                       │
│  │  [audio1][audio2][audio3]...          │                       │
│  └────────┬──────────────────────────────┘                       │
│           │                                                      │
│           ▼                                                      │
│    GET /audio/next                                               │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

1. `POST /synthesize` → validate → push to pending queue (drop oldest if >10)
2. Background worker loop: pull from pending → synthesize with Piper → push to completed buffer
3. `GET /audio/next` → pop from completed buffer → return audio or 204

---

## 5. Configuration

| Setting | Default | Notes |
|---------|---------|-------|
| `MAX_QUEUE_DEPTH` | 10 | Pending queue limit before dropping |
| `PIPER_MODEL_PATH` | `/models/en_US-lessac-medium.onnx` | Piper voice model |
| `PIPER_CONFIG_PATH` | `/models/en_US-lessac-medium.onnx.json` | Piper config |
| `SAMPLE_RATE` | 22050 | Output audio sample rate |
| `AUDIO_FORMAT` | `wav` | Output format |

---

## 6. Dependencies

```
fastapi>=0.109.0
uvicorn>=0.27.0
piper-tts>=1.2.0
pydantic>=2.0.0
```

---

## 7. Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install Piper dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download Piper model (or mount as volume)
RUN mkdir -p /models
# ADD model download step here or mount at runtime

COPY app/ ./app/

EXPOSE 8001

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
```

---

## 8. Implementation Order

| Phase | Tasks |
|-------|-------|
| **Phase 1** | Set up project structure, config, Pydantic models |
| **Phase 2** | Implement `QueueManager` with drop-oldest logic |
| **Phase 3** | Implement `Synthesizer` wrapper for Piper |
| **Phase 4** | Wire up FastAPI endpoints |
| **Phase 5** | Add background worker startup/shutdown lifecycle |
| **Phase 6** | Dockerize + test locally |

---

## 9. Future Enhancements (Post-MVP)

- SSE push instead of polling
- GPU acceleration for Piper
- Voice selection endpoint
- Metrics/observability (Prometheus)
- Health check endpoint (`GET /health`)