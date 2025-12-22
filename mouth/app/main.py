"""FastAPI application for TTS service."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response

from app.config import settings
from app.models import SynthesizeRequest, SynthesizeResponse, QueueItem, QueueStatus
from app.queue_manager import queue_manager
from app.synthesizer import synthesizer

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

    if dropped:
        logger.warning(f"Queue overflow - dropped oldest item for request {request.request_id}")

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
