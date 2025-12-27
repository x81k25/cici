"""Prometheus metrics for MOUTH TTS service."""

from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

# Request metrics
REQUEST_COUNT = Counter(
    "mouth_requests_total",
    "Total requests to MOUTH",
    ["endpoint", "status"]
)

REQUEST_LATENCY = Histogram(
    "mouth_request_latency_seconds",
    "Request latency in seconds",
    ["endpoint"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]
)

# Synthesis metrics
SYNTHESIS_REQUESTS = Counter(
    "mouth_synthesis_requests_total",
    "Total synthesis requests",
    ["status"]
)

SYNTHESIS_LATENCY = Histogram(
    "mouth_synthesis_latency_seconds",
    "TTS synthesis latency per request",
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

# Queue metrics
PENDING_QUEUE_SIZE = Gauge(
    "mouth_pending_queue_size",
    "Items in pending queue"
)

COMPLETED_QUEUE_SIZE = Gauge(
    "mouth_completed_queue_size",
    "Items in completed queue"
)

QUEUE_OVERFLOW = Counter(
    "mouth_queue_overflow_total",
    "Number of items dropped due to queue overflow"
)

# Audio metrics
AUDIO_CHUNKS_SERVED = Counter(
    "mouth_audio_chunks_served_total",
    "Total audio chunks served"
)

AUDIO_BYTES_SERVED = Counter(
    "mouth_audio_bytes_served_total",
    "Total audio bytes served"
)


def get_metrics() -> bytes:
    """Generate Prometheus metrics output."""
    return generate_latest()


def get_content_type() -> str:
    """Get Prometheus content type."""
    return CONTENT_TYPE_LATEST
