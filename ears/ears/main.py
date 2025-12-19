"""
EARS - Pure Transcription WebSocket Service

A simple WebSocket server that receives streaming audio and returns transcriptions.
No command routing, no sessions, no business logic - just audio in, text out.

Protocol:
- Client connects to ws://host:port/
- Client sends binary PCM audio chunks (Int16, 16kHz, mono)
- Server returns JSON transcription messages
- Connection is stateless (no session management)

Expected audio format:
- Raw PCM (no container)
- Int16 samples (16-bit signed little-endian)
- 16000 Hz sample rate
- Mono (1 channel)
"""

# standard library imports
import asyncio
import json
import signal

# 3rd-party imports
from loguru import logger
import websockets
from websockets.server import serve, WebSocketServerProtocol

# local imports
from ears.audio.vad_processor import create_vad_processor
from ears.schemas import ListeningMessage, TranscriptionMessage, ErrorMessage, ClosedMessage


# ------------------------------------------------------------------------------
# WebSocket handler
# ------------------------------------------------------------------------------

async def handle_audio_stream(websocket: WebSocketServerProtocol):
    """
    Handle audio streaming WebSocket connection.

    Receives raw PCM audio chunks, processes through VAD,
    and returns transcriptions when speech segments complete.
    """
    state = {
        "listening": False,
        "chunk_count": 0,
    }

    # Create VAD processor for this connection
    vad_processor = create_vad_processor(min_silence_duration_ms=600)

    async def send_json(message):
        """Send Pydantic model as JSON."""
        try:
            await websocket.send(message.model_dump_json())
        except Exception as e:
            logger.warning(f"failed to send message: {e}")

    try:
        async for message in websocket:
            # Only accept binary audio chunks
            if not isinstance(message, bytes):
                logger.debug("ignoring non-binary message")
                continue

            # Start listening on first chunk
            if not state["listening"]:
                state["listening"] = True
                await send_json(ListeningMessage())
                logger.info("audio listening started")

            state["chunk_count"] += 1

            try:
                # Process audio through VAD
                result = await vad_processor.process_chunk(message)

                if result and result.get("text"):
                    # Speech segment complete - send transcription
                    await send_json(TranscriptionMessage(
                        text=result["text"],
                        final=result.get("final", True)
                    ))

            except Exception as e:
                logger.error(f"error processing audio chunk: {e}")
                # Don't spam errors, just log

    except websockets.ConnectionClosed:
        logger.info("audio stream connection closed")
    except Exception as e:
        logger.exception(f"audio stream error: {e}")
    finally:
        vad_processor.reset()
        logger.debug(f"audio stream cleanup, processed {state['chunk_count']} chunks")


async def handler(websocket: WebSocketServerProtocol):
    """Main WebSocket connection handler."""
    logger.info(f"new connection from {websocket.remote_address}")
    await handle_audio_stream(websocket)


# ------------------------------------------------------------------------------
# server startup
# ------------------------------------------------------------------------------

async def main(host: str = "0.0.0.0", port: int = 8766, ssl_context=None):
    """
    Start the EARS WebSocket server.

    Args:
        host: Host to bind to.
        port: Port to bind to.
        ssl_context: Optional SSL context for secure connections.
    """
    logger.info(f"starting EARS transcription server on {host}:{port}")

    # Handle shutdown gracefully
    stop = asyncio.Event()

    def signal_handler():
        logger.info("shutdown signal received")
        stop.set()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, signal_handler)

    async with serve(handler, host, port, ssl=ssl_context):
        protocol = "wss" if ssl_context else "ws"
        logger.info(f"EARS server running on {protocol}://{host}:{port}")
        logger.info("send raw PCM audio (Int16, 16kHz, mono) to receive transcriptions")
        await stop.wait()

    logger.info("server shutdown complete")


def run_server(host: str = "0.0.0.0", port: int = 8766, ssl_cert: str | None = None, ssl_key: str | None = None):
    """
    Run the EARS WebSocket server (blocking).

    Args:
        host: Host to bind to.
        port: Port to bind to (default 8766, different from main cici server).
        ssl_cert: Path to SSL certificate file.
        ssl_key: Path to SSL key file.
    """
    import ssl

    ssl_context = None
    if ssl_cert and ssl_key:
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_context.load_cert_chain(ssl_cert, ssl_key)
        logger.info(f"SSL enabled with cert: {ssl_cert}")

    asyncio.run(main(host, port, ssl_context))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="EARS transcription server")
    parser.add_argument("--host", default="0.0.0.0", help="host to bind to")
    parser.add_argument("--port", type=int, default=8766, help="port to bind to")
    parser.add_argument("--ssl-cert", help="path to SSL certificate")
    parser.add_argument("--ssl-key", help="path to SSL key")
    parser.add_argument("--debug", action="store_true", help="enable debug logging")

    args = parser.parse_args()

    if args.debug:
        logger.add(lambda msg: print(msg, end=""), level="DEBUG")

    run_server(args.host, args.port, args.ssl_cert, args.ssl_key)


# ------------------------------------------------------------------------------
# end of main.py
# ------------------------------------------------------------------------------
