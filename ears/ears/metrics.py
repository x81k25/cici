"""Prometheus metrics for EARS transcription service."""

import asyncio
from aiohttp import web
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

# Connection metrics
WEBSOCKET_CONNECTIONS = Counter(
    "ears_websocket_connections_total",
    "Total WebSocket connections"
)

ACTIVE_CONNECTIONS = Gauge(
    "ears_active_connections",
    "Current active WebSocket connections"
)

# Audio processing metrics
AUDIO_CHUNKS_RECEIVED = Counter(
    "ears_audio_chunks_received_total",
    "Total audio chunks received"
)

AUDIO_BYTES_RECEIVED = Counter(
    "ears_audio_bytes_received_total",
    "Total audio bytes received"
)

# Transcription metrics
TRANSCRIPTIONS_TOTAL = Counter(
    "ears_transcriptions_total",
    "Total transcriptions produced",
    ["status"]
)

TRANSCRIPTION_LATENCY = Histogram(
    "ears_transcription_latency_seconds",
    "Transcription processing latency",
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

# VAD metrics
VAD_SPEECH_SEGMENTS = Counter(
    "ears_vad_speech_segments_total",
    "Total speech segments detected by VAD"
)

# MIND forwarding metrics
MIND_FORWARDS = Counter(
    "ears_mind_forwards_total",
    "Total transcriptions forwarded to MIND",
    ["status"]
)

# Debug mode metrics
DEBUG_CONNECTIONS = Counter(
    "ears_debug_connections_total",
    "Total debug mode connections"
)


def get_metrics() -> bytes:
    """Generate Prometheus metrics output."""
    return generate_latest()


def get_content_type() -> str:
    """Get Prometheus content type."""
    return CONTENT_TYPE_LATEST


async def metrics_handler(request: web.Request) -> web.Response:
    """Handle /metrics requests."""
    return web.Response(
        body=get_metrics(),
        content_type=get_content_type()
    )


async def health_handler(request: web.Request) -> web.Response:
    """Handle /health requests."""
    return web.Response(
        text='{"status": "healthy", "service": "ears"}',
        content_type="application/json"
    )


async def start_metrics_server(host: str = "0.0.0.0", port: int = 9766):
    """
    Start a lightweight HTTP server for Prometheus metrics.

    Args:
        host: Host to bind to.
        port: Port to bind to (default 9766 = 8766 + 1000).

    Returns:
        The aiohttp Application runner.
    """
    app = web.Application()
    app.router.add_get("/metrics", metrics_handler)
    app.router.add_get("/health", health_handler)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()

    return runner


async def stop_metrics_server(runner):
    """Stop the metrics server."""
    if runner:
        await runner.cleanup()
