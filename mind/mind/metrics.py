"""Prometheus metrics for MIND service."""

from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

# Request metrics
REQUEST_COUNT = Counter(
    "mind_requests_total",
    "Total requests to MIND",
    ["endpoint", "status"]
)

REQUEST_LATENCY = Histogram(
    "mind_request_latency_seconds",
    "Request latency in seconds",
    ["endpoint"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

# Command processing metrics
COMMANDS_PROCESSED = Counter(
    "mind_commands_processed_total",
    "Total commands processed",
    ["route_type"]
)

COMMAND_LATENCY = Histogram(
    "mind_command_latency_seconds",
    "Command processing latency",
    ["route_type"],
    buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0]
)

# Buffer metrics
TRANSCRIPT_BUFFER_SIZE = Gauge(
    "mind_transcript_buffer_words",
    "Current words in transcript buffer"
)

MESSAGE_BUFFER_SIZE = Gauge(
    "mind_message_buffer_count",
    "Current messages in message buffer"
)

# Session metrics
ACTIVE_SESSIONS = Gauge(
    "mind_active_sessions",
    "Number of active sessions"
)

# TTS dispatch metrics
TTS_DISPATCHES = Counter(
    "mind_tts_dispatches_total",
    "Total TTS dispatch calls",
    ["status"]
)


def get_metrics() -> bytes:
    """Generate Prometheus metrics output."""
    return generate_latest()


def get_content_type() -> str:
    """Get Prometheus content type."""
    return CONTENT_TYPE_LATEST
