"""FastAPI application for TTS service."""

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response

from mouth.config import settings
from mouth.models import SynthesizeRequest, SynthesizeResponse, QueueItem, QueueStatus
from mouth.queue_manager import queue_manager
from mouth.synthesizer import synthesizer
from mouth import metrics

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle - start/stop synthesizer."""
    logger.info("Starting TTS service...")
    synthesizer.start()
    yield
    logger.info("Shutting down TTS service...")
    synthesizer.stop()
    queue_manager.clear_all()


app = FastAPI(
    title="TTS Service",
    description="Text-to-Speech microservice using Piper",
    version="1.0.0",
    lifespan=lifespan,
)


# ------------------------------------------------------------------------------
# Metrics middleware
# ------------------------------------------------------------------------------

@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    """Track request metrics."""
    if request.url.path == "/metrics":
        return await call_next(request)

    start_time = time.perf_counter()
    response = await call_next(request)
    duration = time.perf_counter() - start_time

    endpoint = request.url.path
    status = "success" if response.status_code < 400 else "error"

    metrics.REQUEST_COUNT.labels(endpoint=endpoint, status=status).inc()
    metrics.REQUEST_LATENCY.labels(endpoint=endpoint).observe(duration)

    # Update queue gauges on each request
    metrics.PENDING_QUEUE_SIZE.set(queue_manager.pending_count())
    metrics.COMPLETED_QUEUE_SIZE.set(queue_manager.completed_count())

    return response


@app.get("/metrics")
async def prometheus_metrics():
    """Prometheus metrics endpoint."""
    return Response(
        content=metrics.get_metrics(),
        media_type=metrics.get_content_type()
    )


@app.post(
    "/synthesize",
    response_model=SynthesizeResponse,
    status_code=202,
    summary="Queue text for synthesis",
    description="Accepts text and queues it for TTS synthesis. Returns immediately.",
)
async def synthesize(request: SynthesizeRequest) -> SynthesizeResponse:
    """Queue text for synthesis."""
    text = request.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    item = QueueItem(text=text, request_id=request.request_id)
    position, dropped = queue_manager.push_pending(item)

    metrics.SYNTHESIS_REQUESTS.labels(status="queued").inc()

    if dropped:
        logger.warning(f"Queue overflow - dropped oldest item for request {request.request_id}")
        metrics.QUEUE_OVERFLOW.inc()

    return SynthesizeResponse(
        status="queued",
        request_id=request.request_id,
        queue_position=position,
        pending_count=queue_manager.pending_count(),
    )


@app.get(
    "/audio/next",
    summary="Get next completed audio",
    description="Returns the next completed audio chunk, or 204 if none available.",
    responses={
        200: {
            "description": "Audio ready",
            "content": {"audio/wav": {}},
        },
        204: {
            "description": "No audio available",
        },
    },
)
async def get_next_audio() -> Response:
    """Return the next completed audio chunk."""
    chunk = queue_manager.pop_completed()

    headers = {
        "X-Pending-Count": str(queue_manager.pending_count()),
        "X-Completed-Count": str(queue_manager.completed_count()),
    }

    if chunk is None:
        return Response(
            status_code=204,
            headers=headers,
        )

    # Track audio served
    metrics.AUDIO_CHUNKS_SERVED.inc()
    metrics.AUDIO_BYTES_SERVED.inc(len(chunk.audio_data))

    return Response(
        content=chunk.audio_data,
        media_type="audio/wav",
        headers={
            **headers,
            "X-Request-Id": chunk.request_id or "",
        },
    )


@app.get(
    "/status",
    response_model=QueueStatus,
    summary="Get queue status",
    description="Returns the current status of pending and completed queues.",
)
async def get_status() -> QueueStatus:
    """Return queue status."""
    return QueueStatus(
        pending_count=queue_manager.pending_count(),
        completed_count=queue_manager.completed_count(),
    )


@app.get(
    "/health",
    summary="Health check",
    description="Returns service health status.",
)
async def health_check() -> dict:
    """Health check endpoint."""
    return {
        "status": "healthy",
        "synthesizer_running": synthesizer.is_running,
    }
