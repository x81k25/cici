# standard library imports
import asyncio
import json
import multiprocessing
import time
from pathlib import Path

# 3rd-party imports
import pydub
import pytest
import websockets

# local imports - use relative path that works from tests/ or cici/
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "ears"))
from ears.normalize import normalize_transcription


# ------------------------------------------------------------------------------
# constants
# ------------------------------------------------------------------------------

AUDIO_DIR = Path(__file__).parent / "audio"
SERVER_HOST = "localhost"
SERVER_PORT = 18767  # use non-standard port for integration testing
CHUNK_DURATION_MS = 100  # realistic streaming chunk size


# ------------------------------------------------------------------------------
# audio conversion helpers
# ------------------------------------------------------------------------------

def audio_file_to_pcm_chunks(file_path: Path, chunk_duration_ms: int = 100) -> list[bytes]:
    """
    Convert audio file to raw PCM chunks suitable for WebSocket streaming.

    This simulates what FACE *should* do - convert to raw PCM before sending.

    Args:
        file_path: Path to audio file (webm, wav, mp3, etc.)
        chunk_duration_ms: Duration of each chunk in milliseconds.

    Returns:
        List of raw PCM byte chunks (Int16, 16kHz, mono).
    """
    audio = pydub.AudioSegment.from_file(file_path)
    audio = audio.set_frame_rate(16000).set_channels(1).set_sample_width(2)
    raw_pcm = audio.raw_data

    bytes_per_ms = 16000 * 2 / 1000
    chunk_size = int(bytes_per_ms * chunk_duration_ms)

    chunks = []
    for i in range(0, len(raw_pcm), chunk_size):
        chunks.append(raw_pcm[i:i + chunk_size])

    return chunks


def audio_file_to_raw_webm_chunks(file_path: Path, chunk_size: int = 4096) -> list[bytes]:
    """
    Read WebM file and chunk it directly (no conversion).

    This simulates what FACE actually does - sends raw WebM/Opus chunks
    from MediaRecorder without conversion to PCM.

    Args:
        file_path: Path to WebM audio file.
        chunk_size: Size of each chunk in bytes.

    Returns:
        List of raw WebM byte chunks (NOT PCM - this is the problem!).
    """
    with open(file_path, "rb") as f:
        data = f.read()

    chunks = []
    for i in range(0, len(data), chunk_size):
        chunks.append(data[i:i + chunk_size])

    return chunks


# ------------------------------------------------------------------------------
# server management
# ------------------------------------------------------------------------------

def run_server_process(host: str, port: int, ready_event: multiprocessing.Event):
    """Run the EARS server in a subprocess."""
    import asyncio
    sys.path.insert(0, str(Path(__file__).parent.parent / "ears"))
    from ears.main import main

    async def server_main():
        ready_event.set()
        await main(host=host, port=port)

    asyncio.run(server_main())


@pytest.fixture(scope="module")
def ears_server():
    """Start EARS server for the test module, shut down after."""
    ready_event = multiprocessing.Event()
    server_process = multiprocessing.Process(
        target=run_server_process,
        args=(SERVER_HOST, SERVER_PORT, ready_event),
        daemon=True,
    )
    server_process.start()

    # wait for server to be ready
    ready_event.wait(timeout=30)
    time.sleep(2)  # give server time to fully initialize (model loading)

    yield f"ws://{SERVER_HOST}:{SERVER_PORT}"

    # shutdown
    server_process.terminate()
    server_process.join(timeout=5)
    if server_process.is_alive():
        server_process.kill()


# ------------------------------------------------------------------------------
# test data loading
# ------------------------------------------------------------------------------

def load_transcription_test_cases() -> list[dict]:
    """Load transcription test cases from JSON file."""
    transcriptions_file = AUDIO_DIR / "transcriptions.json"
    if not transcriptions_file.exists():
        return []

    with open(transcriptions_file, "r") as f:
        return json.load(f)


def get_test_case_ids() -> list[str]:
    """Get test IDs for parametrization."""
    cases = load_transcription_test_cases()
    return [case["filename"] for case in cases]


def get_test_case_params() -> list[tuple[str, str]]:
    """Get (filename, expected_transcription) tuples for parametrization."""
    cases = load_transcription_test_cases()
    return [(case["filename"], case["transcription"]) for case in cases]


# ------------------------------------------------------------------------------
# helper functions
# ------------------------------------------------------------------------------

def normalize_text(text: str) -> str:
    """Normalize transcription text for comparison."""
    import re
    text = normalize_transcription(text)  # apply word aliases
    text = text.lower()
    text = re.sub(r'[^\w\s]', '', text)  # remove punctuation
    text = re.sub(r'\s+', ' ', text).strip()  # collapse whitespace
    return text


async def stream_and_collect_transcriptions(
    ws_url: str,
    chunks: list[bytes],
    chunk_delay_ms: int = 100,
    silence_bytes: bytes | None = None,
    timeout: float = 30.0,
    debug: bool = True,
) -> tuple[list[str], list[dict], list[dict]]:
    """
    Stream audio chunks to EARS and collect transcription responses.

    Args:
        ws_url: WebSocket URL of EARS server.
        chunks: List of audio byte chunks to send.
        chunk_delay_ms: Delay between chunks in milliseconds.
        silence_bytes: Optional silence to append after chunks.
        timeout: Maximum time to wait for transcription.
        debug: Enable debug mode to receive per-chunk analysis (default True).

    Returns:
        Tuple of (transcription texts, all raw messages, debug messages).
    """
    # Append debug query parameter to URL
    url = f"{ws_url}?debug={str(debug).lower()}"

    transcriptions = []
    all_messages = []
    debug_messages = []
    transcription_received = asyncio.Event()

    async with websockets.connect(url) as ws:
        async def collect_responses():
            try:
                async for message in ws:
                    data = json.loads(message)
                    all_messages.append(data)
                    if data.get("type") == "transcription":
                        transcriptions.append(data.get("text", ""))
                        transcription_received.set()
                    elif data.get("type") == "debug":
                        debug_messages.append(data)
            except websockets.ConnectionClosed:
                pass

        collector = asyncio.create_task(collect_responses())

        # stream chunks with realistic timing
        for chunk in chunks:
            await ws.send(chunk)
            await asyncio.sleep(chunk_delay_ms / 1000)

        # send silence to trigger VAD finalization
        if silence_bytes:
            await ws.send(silence_bytes)

        # wait for transcription
        try:
            await asyncio.wait_for(transcription_received.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            pass

        # close and cleanup
        await ws.close()
        collector.cancel()
        try:
            await collector
        except asyncio.CancelledError:
            pass

    return transcriptions, all_messages, debug_messages


# ------------------------------------------------------------------------------
# integration tests: PCM streaming (proper format)
# ------------------------------------------------------------------------------

class TestPCMStreaming:
    """
    Tests streaming properly-converted PCM audio to EARS.

    This simulates what FACE *should* do - convert browser audio to PCM
    before sending. These tests should pass.
    """

    @pytest.mark.slow
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "filename,expected_transcription",
        get_test_case_params(),
        ids=get_test_case_ids(),
    )
    async def test_pcm_stream_produces_transcription(
        self,
        ears_server: str,
        filename: str,
        expected_transcription: str,
    ):
        """Stream PCM-converted audio and verify transcription matches."""
        audio_path = AUDIO_DIR / filename
        if not audio_path.exists():
            pytest.skip(f"Audio file not found: {audio_path}")

        # Convert to PCM chunks (this is what FACE should do)
        chunks = audio_file_to_pcm_chunks(audio_path, CHUNK_DURATION_MS)

        # Stream with trailing silence to trigger transcription (debug=True by default)
        silence = b"\x00" * (16000 * 2)  # 1 second of silence
        transcriptions, messages, debug_msgs = await stream_and_collect_transcriptions(
            ears_server,
            chunks,
            chunk_delay_ms=CHUNK_DURATION_MS,
            silence_bytes=silence,
        )

        # Verify we got the "listening" message
        listening_msgs = [m for m in messages if m.get("type") == "listening"]
        assert len(listening_msgs) > 0, "Server should send 'listening' message on first chunk"

        # Verify debug messages were received (debug mode enabled)
        assert len(debug_msgs) > 0, "Should receive debug messages when debug=true"

        # Verify we got transcription
        assert len(transcriptions) > 0, f"No transcriptions received for {filename}"

        # Compare transcriptions
        full_transcription = " ".join(transcriptions).strip()
        result_normalized = normalize_text(full_transcription)
        expected_normalized = normalize_text(expected_transcription)

        assert expected_normalized in result_normalized or result_normalized in expected_normalized, (
            f"Transcription mismatch for {filename}:\n"
            f"  Expected: {expected_transcription}\n"
            f"  Got: {full_transcription}"
        )


# ------------------------------------------------------------------------------
# integration tests: raw WebM streaming (simulates browser behavior)
# ------------------------------------------------------------------------------

class TestRawWebMStreaming:
    """
    Tests streaming raw WebM chunks directly (like browser MediaRecorder does).

    This simulates what FACE *actually* does - sending WebM/Opus chunks
    without conversion to PCM. These tests demonstrate the format mismatch issue.
    """

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_raw_webm_produces_no_transcription(self, ears_server: str):
        """
        Stream raw WebM chunks (no conversion) and verify no transcription.

        This test demonstrates the current issue: FACE sends WebM/Opus,
        but EARS expects raw PCM. The result is garbage audio data
        that produces no speech detection.
        """
        # Use the first test file
        test_cases = load_transcription_test_cases()
        if not test_cases:
            pytest.skip("No test audio files available")

        audio_path = AUDIO_DIR / test_cases[0]["filename"]
        if not audio_path.exists():
            pytest.skip(f"Audio file not found: {audio_path}")

        # Send raw WebM chunks (this is what FACE actually does)
        chunks = audio_file_to_raw_webm_chunks(audio_path, chunk_size=4096)

        # Stream without conversion (debug=True by default)
        transcriptions, messages, debug_msgs = await stream_and_collect_transcriptions(
            ears_server,
            chunks,
            chunk_delay_ms=50,  # faster since we're just testing
            silence_bytes=b"\x00" * (16000 * 2),  # 1 second silence
            timeout=10.0,  # shorter timeout - we expect no transcription
        )

        # Verify we connected (should get listening message)
        listening_msgs = [m for m in messages if m.get("type") == "listening"]
        assert len(listening_msgs) > 0, "Server should accept connection and start listening"

        # Verify debug messages were received
        assert len(debug_msgs) > 0, "Should receive debug messages when debug=true"

        # This is the key assertion: raw WebM produces NO transcription
        # because EARS interprets the WebM bytes as garbage PCM data
        assert len(transcriptions) == 0, (
            "Raw WebM streaming should NOT produce transcriptions (format mismatch). "
            f"Got: {transcriptions}"
        )

    @pytest.mark.slow
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "filename,expected_transcription",
        get_test_case_params()[:1],  # Just test first file
        ids=get_test_case_ids()[:1],
    )
    async def test_webm_vs_pcm_comparison(
        self,
        ears_server: str,
        filename: str,
        expected_transcription: str,
    ):
        """
        Compare WebM vs PCM streaming to demonstrate format difference.

        This test shows that the same audio file produces different results
        depending on whether it's converted to PCM or sent raw.
        """
        audio_path = AUDIO_DIR / filename
        if not audio_path.exists():
            pytest.skip(f"Audio file not found: {audio_path}")

        # Test 1: Stream as raw WebM (FACE's current behavior)
        webm_chunks = audio_file_to_raw_webm_chunks(audio_path)
        webm_transcriptions, _, webm_debug = await stream_and_collect_transcriptions(
            ears_server,
            webm_chunks,
            chunk_delay_ms=50,
            silence_bytes=b"\x00" * (16000 * 2),
            timeout=10.0,
        )

        # Need to wait a bit between tests for VAD to reset
        await asyncio.sleep(1)

        # Test 2: Stream as PCM (correct behavior)
        pcm_chunks = audio_file_to_pcm_chunks(audio_path)
        pcm_transcriptions, _, pcm_debug = await stream_and_collect_transcriptions(
            ears_server,
            pcm_chunks,
            chunk_delay_ms=CHUNK_DURATION_MS,
            silence_bytes=b"\x00" * (16000 * 2),
            timeout=30.0,
        )

        # Verify debug messages were received for both
        assert len(webm_debug) > 0, "Should receive debug messages for WebM streaming"
        assert len(pcm_debug) > 0, "Should receive debug messages for PCM streaming"

        # Verify the difference
        assert len(pcm_transcriptions) > 0, "PCM streaming should produce transcription"
        assert len(webm_transcriptions) == 0, "Raw WebM should NOT produce transcription"

        # Verify PCM transcription matches expected
        pcm_text = " ".join(pcm_transcriptions)
        assert normalize_text(expected_transcription) in normalize_text(pcm_text) or \
               normalize_text(pcm_text) in normalize_text(expected_transcription)


# ------------------------------------------------------------------------------
# integration tests: WebSocket protocol
# ------------------------------------------------------------------------------

class TestWebSocketProtocol:
    """Tests for the EARS WebSocket protocol behavior."""

    @pytest.mark.asyncio
    async def test_server_sends_listening_on_first_chunk(self, ears_server: str):
        """Verify server sends 'listening' message on first audio chunk."""
        async with websockets.connect(f"{ears_server}?debug=true") as ws:
            # Send a small audio chunk
            await ws.send(b"\x00" * 3200)  # 100ms of silence

            # Should receive listening message
            response = await asyncio.wait_for(ws.recv(), timeout=5.0)
            data = json.loads(response)

            assert data["type"] == "listening"
            assert "sample_rate" in data

    @pytest.mark.asyncio
    async def test_server_ignores_text_messages(self, ears_server: str):
        """Verify server ignores text messages (only accepts binary)."""
        async with websockets.connect(f"{ears_server}?debug=true") as ws:
            # Send text message (should be ignored)
            await ws.send('{"type": "test"}')

            # Send binary to trigger listening response
            await ws.send(b"\x00" * 3200)

            # Should get listening message
            response = await asyncio.wait_for(ws.recv(), timeout=5.0)
            data = json.loads(response)

            # Verify we got listening (not an error about text message)
            assert data["type"] == "listening"

    @pytest.mark.asyncio
    async def test_connection_accepts_multiple_chunks(self, ears_server: str):
        """Verify server can handle continuous chunk streaming."""
        chunk_count = 10
        chunks_sent = 0
        debug_msgs = []

        async with websockets.connect(f"{ears_server}?debug=true") as ws:
            for _ in range(chunk_count):
                await ws.send(b"\x00" * 3200)  # 100ms silence chunks
                chunks_sent += 1
                await asyncio.sleep(0.1)

            # Collect all messages (listening + debug messages)
            messages = []
            try:
                while True:
                    response = await asyncio.wait_for(ws.recv(), timeout=1.0)
                    data = json.loads(response)
                    messages.append(data)
                    if data.get("type") == "debug":
                        debug_msgs.append(data)
            except asyncio.TimeoutError:
                pass

        assert chunks_sent == chunk_count
        # Should have listening message
        listening_msgs = [m for m in messages if m.get("type") == "listening"]
        assert len(listening_msgs) > 0, "Should receive listening message"
        # Should have debug messages
        assert len(debug_msgs) > 0, "Should receive debug messages when debug=true"

    @pytest.mark.asyncio
    async def test_multiple_connections_independent(self, ears_server: str):
        """Verify multiple WebSocket connections are handled independently."""
        async def connect_and_send():
            async with websockets.connect(f"{ears_server}?debug=true") as ws:
                await ws.send(b"\x00" * 3200)
                response = await asyncio.wait_for(ws.recv(), timeout=5.0)
                return json.loads(response)

        # Create multiple concurrent connections
        results = await asyncio.gather(
            connect_and_send(),
            connect_and_send(),
            connect_and_send(),
        )

        # All should receive listening messages
        for result in results:
            assert result["type"] == "listening"

    @pytest.mark.asyncio
    async def test_debug_mode_sends_debug_messages(self, ears_server: str):
        """Verify debug mode sends per-chunk analysis messages."""
        async with websockets.connect(f"{ears_server}?debug=true") as ws:
            # Send a chunk
            await ws.send(b"\x00" * 3200)

            # Collect messages
            messages = []
            try:
                while True:
                    response = await asyncio.wait_for(ws.recv(), timeout=2.0)
                    messages.append(json.loads(response))
            except asyncio.TimeoutError:
                pass

        # Should have both listening and debug messages
        msg_types = [m.get("type") for m in messages]
        assert "listening" in msg_types, "Should receive listening message"
        assert "debug" in msg_types, "Should receive debug message when debug=true"

        # Verify debug message structure
        debug_msgs = [m for m in messages if m.get("type") == "debug"]
        assert len(debug_msgs) > 0
        debug_msg = debug_msgs[0]
        assert "chunk_index" in debug_msg
        assert "sample_count" in debug_msg
        assert "duration_ms" in debug_msg
        assert "defects" in debug_msg
        assert "metrics" in debug_msg


# ------------------------------------------------------------------------------
# integration tests: simulated FACE streaming behavior
# ------------------------------------------------------------------------------

class TestSimulatedFaceStreaming:
    """
    Tests that simulate FACE's actual streaming behavior.

    These tests help diagnose why audio from FACE shows "no speech".
    """

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_chunked_pcm_with_realistic_timing(self, ears_server: str):
        """
        Simulate realistic FACE streaming with proper PCM conversion.

        Uses 500ms chunks (FACE's default) with realistic timing.
        """
        test_cases = load_transcription_test_cases()
        if not test_cases:
            pytest.skip("No test audio files available")

        audio_path = AUDIO_DIR / test_cases[0]["filename"]
        if not audio_path.exists():
            pytest.skip(f"Audio file not found: {audio_path}")

        # Use FACE's default chunk duration (500ms)
        chunks = audio_file_to_pcm_chunks(audio_path, chunk_duration_ms=500)

        transcriptions, messages, debug_msgs = await stream_and_collect_transcriptions(
            ears_server,
            chunks,
            chunk_delay_ms=500,  # realistic timing
            silence_bytes=b"\x00" * (16000 * 2),
            timeout=30.0,
        )

        # Verify debug messages were received
        assert len(debug_msgs) > 0, "Should receive debug messages when debug=true"

        assert len(transcriptions) > 0, (
            "Should receive transcription with realistic FACE timing. "
            f"Messages received: {[m['type'] for m in messages]}"
        )

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_varying_chunk_sizes(self, ears_server: str):
        """Test VAD handles varying chunk sizes correctly."""
        test_cases = load_transcription_test_cases()
        if not test_cases:
            pytest.skip("No test audio files available")

        audio_path = AUDIO_DIR / test_cases[0]["filename"]
        if not audio_path.exists():
            pytest.skip(f"Audio file not found: {audio_path}")

        # Load full audio
        audio = pydub.AudioSegment.from_file(audio_path)
        audio = audio.set_frame_rate(16000).set_channels(1).set_sample_width(2)
        raw_pcm = audio.raw_data

        # Create varying size chunks (simulates network jitter)
        import random
        random.seed(42)  # reproducible

        chunks = []
        pos = 0
        while pos < len(raw_pcm):
            # Vary between 50ms and 200ms chunks
            chunk_ms = random.randint(50, 200)
            chunk_bytes = int(16000 * 2 * chunk_ms / 1000)
            chunks.append(raw_pcm[pos:pos + chunk_bytes])
            pos += chunk_bytes

        transcriptions, _, debug_msgs = await stream_and_collect_transcriptions(
            ears_server,
            chunks,
            chunk_delay_ms=100,  # average timing
            silence_bytes=b"\x00" * (16000 * 2),
            timeout=30.0,
        )

        # Verify debug messages were received
        assert len(debug_msgs) > 0, "Should receive debug messages when debug=true"

        assert len(transcriptions) > 0, "VAD should handle varying chunk sizes"


# ------------------------------------------------------------------------------
# defect test data loading
# ------------------------------------------------------------------------------

DEFECT_AUDIO_DIR = AUDIO_DIR / "defective"


def load_defect_test_cases() -> list[dict]:
    """Load defect test cases from JSON file."""
    defects_file = DEFECT_AUDIO_DIR / "defects.json"
    if not defects_file.exists():
        return []

    with open(defects_file, "r") as f:
        return json.load(f)


def get_defect_test_params() -> list[tuple[str, str]]:
    """Get (filename, defect_type) tuples for parametrization."""
    cases = load_defect_test_cases()
    return [(case["filename"], case["defect_type"]) for case in cases]


def get_defect_test_ids() -> list[str]:
    """Get test IDs for defect parametrization."""
    cases = load_defect_test_cases()
    return [case["filename"] for case in cases]


# ------------------------------------------------------------------------------
# integration tests: defect detection (debug mode)
# ------------------------------------------------------------------------------

class TestDefectDetection:
    """
    Tests that EARS correctly detects and reports audio defects via debug mode.

    Uses defective audio files from tests/audio/defective/ to verify
    the AudioAnalyzer returns appropriate defect codes.
    """

    @pytest.mark.slow
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "filename,expected_defect",
        get_defect_test_params(),
        ids=get_defect_test_ids(),
    )
    async def test_defect_detection(
        self,
        ears_server: str,
        filename: str,
        expected_defect: str,
    ):
        """Stream defective audio and verify correct defect is detected."""
        audio_path = DEFECT_AUDIO_DIR / filename
        if not audio_path.exists():
            pytest.skip(f"Defect audio file not found: {audio_path}")

        # Handle raw PCM files differently
        if filename.endswith(".raw"):
            with open(audio_path, "rb") as f:
                raw_pcm = f.read()
            # Chunk the raw PCM
            chunk_size = int(16000 * 2 * CHUNK_DURATION_MS / 1000)
            chunks = [raw_pcm[i:i + chunk_size] for i in range(0, len(raw_pcm), chunk_size)]
        else:
            # Convert WebM to PCM chunks
            chunks = audio_file_to_pcm_chunks(audio_path, CHUNK_DURATION_MS)

        # Stream with debug mode enabled
        transcriptions, messages, debug_msgs = await stream_and_collect_transcriptions(
            ears_server,
            chunks,
            chunk_delay_ms=CHUNK_DURATION_MS,
            silence_bytes=b"\x00" * (16000 * 2),
            debug=True,
        )

        # Verify we got debug messages
        assert len(debug_msgs) > 0, f"No debug messages received for {filename}"

        # Collect all defect codes from debug messages
        all_defects = []
        for msg in debug_msgs:
            if "defects" in msg:
                for defect in msg["defects"]:
                    all_defects.append({
                        "code": defect["code"],
                        "severity": defect["severity"],
                        "message": defect.get("message", ""),
                        "value": defect.get("value"),
                        "threshold": defect.get("threshold"),
                    })

        # Verify the expected defect was detected
        defect_codes = [d["code"] for d in all_defects]
        assert expected_defect in defect_codes, (
            f"Expected defect '{expected_defect}' not found for {filename}.\n"
            f"Detected defects: {defect_codes}\n"
            f"All defect details: {all_defects}"
        )

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_clean_audio_no_error_defects(self, ears_server: str):
        """Verify clean audio produces no error-level defects (warnings acceptable)."""
        test_cases = load_transcription_test_cases()
        if not test_cases:
            pytest.skip("No test audio files available")

        audio_path = AUDIO_DIR / test_cases[0]["filename"]
        if not audio_path.exists():
            pytest.skip(f"Audio file not found: {audio_path}")

        chunks = audio_file_to_pcm_chunks(audio_path, CHUNK_DURATION_MS)

        transcriptions, messages, debug_msgs = await stream_and_collect_transcriptions(
            ears_server,
            chunks,
            chunk_delay_ms=CHUNK_DURATION_MS,
            silence_bytes=b"\x00" * (16000 * 2),
            debug=True,
        )

        # Collect error-severity defects (warnings are acceptable)
        # Exclude 'silence' errors - natural speech has silent portions at start/end
        error_defects = []
        for msg in debug_msgs:
            if "defects" in msg:
                for defect in msg["defects"]:
                    if defect.get("severity") == "error" and defect.get("code") != "silence":
                        error_defects.append(defect)

        # Clean audio should have no error-level defects (except silence)
        assert len(error_defects) == 0, (
            f"Clean audio should not have error-level defects (excluding silence).\n"
            f"Found: {error_defects}"
        )

    @pytest.mark.asyncio
    async def test_debug_message_structure(self, ears_server: str):
        """Verify debug messages have correct structure."""
        test_cases = load_transcription_test_cases()
        if not test_cases:
            pytest.skip("No test audio files available")

        audio_path = AUDIO_DIR / test_cases[0]["filename"]
        chunks = audio_file_to_pcm_chunks(audio_path, CHUNK_DURATION_MS)[:5]  # Just 5 chunks

        _, _, debug_msgs = await stream_and_collect_transcriptions(
            ears_server,
            chunks,
            chunk_delay_ms=CHUNK_DURATION_MS,
            debug=True,
        )

        assert len(debug_msgs) > 0, "Should receive debug messages"

        # Verify structure of first debug message
        msg = debug_msgs[0]
        assert msg["type"] == "debug"
        assert "chunk_index" in msg
        assert "sample_count" in msg
        assert "duration_ms" in msg
        assert "defects" in msg
        assert "metrics" in msg

        # Verify metrics structure
        metrics = msg["metrics"]
        expected_metrics = ["rms", "peak", "dc_offset", "clipping_ratio", "zero_crossing_rate", "spectral_centroid"]
        for metric in expected_metrics:
            assert metric in metrics, f"Missing metric: {metric}"

    @pytest.mark.asyncio
    async def test_defect_severity_values(self, ears_server: str):
        """Verify defect severity values are either 'warning' or 'error'."""
        # Use silence audio which will trigger 'silence' defect (error level)
        silence_path = DEFECT_AUDIO_DIR / "defect_silence.webm"
        if not silence_path.exists():
            pytest.skip("Silence defect file not found")

        chunks = audio_file_to_pcm_chunks(silence_path, CHUNK_DURATION_MS)

        _, _, debug_msgs = await stream_and_collect_transcriptions(
            ears_server,
            chunks,
            chunk_delay_ms=CHUNK_DURATION_MS,
            debug=True,
        )

        # Collect all defects
        all_defects = []
        for msg in debug_msgs:
            if "defects" in msg:
                all_defects.extend(msg["defects"])

        # Verify we have defects and all have valid severity
        assert len(all_defects) > 0, "Should detect defects in silence audio"
        for defect in all_defects:
            assert defect["severity"] in ("warning", "error"), (
                f"Invalid severity: {defect['severity']}"
            )

    @pytest.mark.asyncio
    async def test_metrics_values_are_numeric(self, ears_server: str):
        """Verify all metrics values are numeric."""
        test_cases = load_transcription_test_cases()
        if not test_cases:
            pytest.skip("No test audio files available")

        audio_path = AUDIO_DIR / test_cases[0]["filename"]
        chunks = audio_file_to_pcm_chunks(audio_path, CHUNK_DURATION_MS)[:3]

        _, _, debug_msgs = await stream_and_collect_transcriptions(
            ears_server,
            chunks,
            chunk_delay_ms=CHUNK_DURATION_MS,
            debug=True,
        )

        assert len(debug_msgs) > 0, "Should receive debug messages"

        for msg in debug_msgs:
            metrics = msg["metrics"]
            for key, value in metrics.items():
                assert isinstance(value, (int, float)), (
                    f"Metric '{key}' should be numeric, got {type(value)}: {value}"
                )
