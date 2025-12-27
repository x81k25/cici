"""Prometheus metrics for FACE frontend service."""

import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from prometheus_client import Counter, Gauge, generate_latest, CONTENT_TYPE_LATEST

# Session metrics
ACTIVE_SESSIONS = Gauge(
    "face_active_sessions",
    "Current active Streamlit sessions"
)

# User interaction metrics
MESSAGES_SENT = Counter(
    "face_messages_sent_total",
    "Total messages sent to MIND",
    ["input_type"]  # text, voice
)

MESSAGES_RECEIVED = Counter(
    "face_messages_received_total",
    "Total messages received from MIND",
    ["message_type"]  # llm_response, cli_result, system, error
)

# Audio metrics
AUDIO_PLAYBACKS = Counter(
    "face_audio_playbacks_total",
    "Total audio chunks played"
)

# Connection metrics
MIND_REQUESTS = Counter(
    "face_mind_requests_total",
    "Total requests to MIND API",
    ["endpoint", "status"]
)

EARS_CONNECTIONS = Counter(
    "face_ears_connections_total",
    "Total WebSocket connections to EARS",
    ["status"]
)

MOUTH_REQUESTS = Counter(
    "face_mouth_requests_total",
    "Total requests to MOUTH API",
    ["endpoint", "status"]
)

# Error metrics
ERRORS = Counter(
    "face_errors_total",
    "Total errors",
    ["error_type"]
)


def get_metrics() -> bytes:
    """Generate Prometheus metrics output."""
    return generate_latest()


def get_content_type() -> str:
    """Get Prometheus content type."""
    return CONTENT_TYPE_LATEST


class MetricsHandler(BaseHTTPRequestHandler):
    """HTTP handler for Prometheus metrics."""

    def log_message(self, format, *args):
        """Suppress default logging."""
        pass

    def do_GET(self):
        """Handle GET requests."""
        if self.path == "/metrics":
            content = get_metrics()
            self.send_response(200)
            self.send_header("Content-Type", get_content_type())
            self.send_header("Content-Length", len(content))
            self.end_headers()
            self.wfile.write(content)
        elif self.path == "/health":
            content = b'{"status": "healthy", "service": "face"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", len(content))
            self.end_headers()
            self.wfile.write(content)
        else:
            self.send_error(404)


_server = None
_server_thread = None


def start_metrics_server(host: str = "0.0.0.0", port: int = 9501):
    """
    Start metrics HTTP server in a background thread.

    Args:
        host: Host to bind to.
        port: Port to bind to (default 9501 = 8501 + 1000).
    """
    global _server, _server_thread

    if _server is not None:
        return  # Already running

    _server = HTTPServer((host, port), MetricsHandler)
    _server_thread = threading.Thread(target=_server.serve_forever, daemon=True)
    _server_thread.start()


def stop_metrics_server():
    """Stop the metrics server."""
    global _server, _server_thread

    if _server is not None:
        _server.shutdown()
        _server = None
        _server_thread = None
