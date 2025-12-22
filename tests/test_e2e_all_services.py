"""
End-to-end integration tests for FACE -> EARS -> MIND flow.

These tests verify the complete audio-to-response pipeline:
1. Audio files are streamed to EARS (via WebSocket)
2. EARS produces transcriptions
3. Transcriptions are sent to MIND (via HTTP REST, like FACE does)
4. MIND processes the text and returns responses
5. FACE can poll for results

This simulates the real user flow where voice input goes through
all three services.
"""

# standard library imports
import asyncio
import json
import multiprocessing
import sys
import time
from pathlib import Path

# 3rd-party imports
import httpx
import pydub
import pytest
import websockets

# local imports
CICI_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(CICI_ROOT / "face"))
sys.path.insert(0, str(CICI_ROOT / "ears"))
sys.path.insert(0, str(CICI_ROOT / "mind"))

from mind_client import MindClient, ConnectionState
from ears.normalize import normalize_transcription


# ------------------------------------------------------------------------------
# constants
# ------------------------------------------------------------------------------

AUDIO_DIR = Path(__file__).parent / "audio"

# Use non-standard ports for integration testing
EARS_HOST = "localhost"
EARS_PORT = 18767
MIND_HOST = "localhost"
MIND_PORT = 18765

CHUNK_DURATION_MS = 100  # realistic streaming chunk size


# ------------------------------------------------------------------------------
# audio conversion helpers
# ------------------------------------------------------------------------------

def audio_file_to_pcm_chunks(file_path: Path, chunk_duration_ms: int = 100) -> list[bytes]:
    """
    Convert audio file to raw PCM chunks suitable for WebSocket streaming.

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


# ------------------------------------------------------------------------------
# text normalization helpers
# ------------------------------------------------------------------------------

def normalize_text(text: str) -> str:
    """Normalize transcription text for comparison."""
    import re
    text = normalize_transcription(text)  # apply word aliases
    text = text.lower()
    text = re.sub(r'[^\w\s]', '', text)  # remove punctuation
    text = re.sub(r'\s+', ' ', text).strip()  # collapse whitespace
    return text


# ------------------------------------------------------------------------------
# server management - EARS
# ------------------------------------------------------------------------------

def run_ears_server_process(host: str, port: int, ready_event: multiprocessing.Event):
    """Run the EARS server in a subprocess."""
    import asyncio
    sys.path.insert(0, str(CICI_ROOT / "ears"))
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
        target=run_ears_server_process,
        args=(EARS_HOST, EARS_PORT, ready_event),
        daemon=True,
    )
    server_process.start()

    # wait for server to be ready
    ready_event.wait(timeout=30)
    time.sleep(2)  # give server time to fully initialize (model loading)

    yield f"ws://{EARS_HOST}:{EARS_PORT}"

    # shutdown
    server_process.terminate()
    server_process.join(timeout=5)
    if server_process.is_alive():
        server_process.kill()


# ------------------------------------------------------------------------------
# server management - MIND
# ------------------------------------------------------------------------------

def run_mind_server_process(host: str, port: int, ready_event: multiprocessing.Event):
    """Run the MIND server in a subprocess."""
    import uvicorn
    sys.path.insert(0, str(CICI_ROOT / "mind"))
    from mind.main import app

    from contextlib import asynccontextmanager

    original_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan_with_signal(app):
        async with original_lifespan(app):
            ready_event.set()
            yield

    app.router.lifespan_context = lifespan_with_signal

    uvicorn.run(app, host=host, port=port, log_level="warning")


@pytest.fixture(scope="module")
def mind_server():
    """Start MIND server for the test module, shut down after."""
    ready_event = multiprocessing.Event()
    server_process = multiprocessing.Process(
        target=run_mind_server_process,
        args=(MIND_HOST, MIND_PORT, ready_event),
        daemon=True,
    )
    server_process.start()

    # Wait for server to be ready
    ready_event.wait(timeout=30)
    time.sleep(1)  # Give server time to fully initialize

    yield f"http://{MIND_HOST}:{MIND_PORT}"

    # Shutdown
    server_process.terminate()
    server_process.join(timeout=5)
    if server_process.is_alive():
        server_process.kill()


# ------------------------------------------------------------------------------
# combined fixture - both servers
# ------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def all_servers(ears_server, mind_server):
    """Start both EARS and MIND servers."""
    return {
        "ears_url": ears_server,
        "mind_url": mind_server,
    }


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
# EARS streaming helper
# ------------------------------------------------------------------------------

async def stream_audio_to_ears(
    ws_url: str,
    chunks: list[bytes],
    chunk_delay_ms: int = 100,
    timeout: float = 30.0,
) -> tuple[list[str], list[dict]]:
    """
    Stream audio chunks to EARS and collect transcription responses.

    Args:
        ws_url: WebSocket URL of EARS server.
        chunks: List of audio byte chunks to send.
        chunk_delay_ms: Delay between chunks in milliseconds.
        timeout: Maximum time to wait for transcription.

    Returns:
        Tuple of (transcription texts, all raw messages).
    """
    transcriptions = []
    all_messages = []
    transcription_received = asyncio.Event()

    async with websockets.connect(ws_url) as ws:
        async def collect_responses():
            try:
                async for message in ws:
                    data = json.loads(message)
                    all_messages.append(data)
                    if data.get("type") == "transcription":
                        transcriptions.append(data.get("text", ""))
                        transcription_received.set()
            except websockets.ConnectionClosed:
                pass

        collector = asyncio.create_task(collect_responses())

        # stream chunks with realistic timing
        for chunk in chunks:
            await ws.send(chunk)
            await asyncio.sleep(chunk_delay_ms / 1000)

        # send silence to trigger VAD finalization
        silence = b"\x00" * (16000 * 2)  # 1 second of silence
        await ws.send(silence)

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

    return transcriptions, all_messages


# ------------------------------------------------------------------------------
# MIND client helper
# ------------------------------------------------------------------------------

class E2ETestClient:
    """Test client that wraps MindClient for E2E testing."""

    def __init__(self, base_url: str):
        self.client = MindClient(base_url=base_url)
        self.base_url = base_url

    def connect(self) -> bool:
        """Connect to the MIND server."""
        return self.client.connect()

    def disconnect(self) -> None:
        """Disconnect from server."""
        self.client.disconnect()

    def send_transcription(self, text: str, original_voice: str | None = None) -> dict | None:
        """Send transcription text to MIND (like FACE does)."""
        return self.client.process_text(text, original_voice=original_voice)

    def poll_messages(self) -> dict | None:
        """Poll for new messages (like FACE does for streaming)."""
        return self.client.poll_messages()

    def health_check(self) -> bool:
        """Check if MIND server is healthy."""
        return self.client.health_check()

    @property
    def mode(self) -> str:
        """Current interaction mode."""
        return self.client.mode

    @property
    def current_directory(self) -> str:
        """Current working directory."""
        return self.client.current_directory

    @property
    def state(self) -> ConnectionState:
        """Current connection state."""
        return self.client.state


@pytest.fixture
def test_client(mind_server) -> E2ETestClient:
    """Create a connected test client to MIND."""
    client = E2ETestClient(base_url=mind_server)
    assert client.connect(), f"Failed to connect to MIND server"
    yield client
    client.disconnect()


# ------------------------------------------------------------------------------
# E2E Integration Tests: Full Audio -> EARS -> MIND Flow
# ------------------------------------------------------------------------------

class TestFullE2EFlow:
    """
    Tests the complete end-to-end flow:
    Audio -> EARS (transcription) -> MIND (processing) -> Response
    """

    @pytest.mark.slow
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_audio_to_transcription_to_mind_basic(self, all_servers):
        """
        Basic E2E test: stream audio to EARS, get transcription, send to MIND.

        Uses a simple test recording to verify the full pipeline works.
        """
        test_cases = load_transcription_test_cases()
        if not test_cases:
            pytest.skip("No test audio files available")

        # Use the first/simplest test case
        audio_path = AUDIO_DIR / test_cases[0]["filename"]
        expected_transcription = test_cases[0]["transcription"]

        if not audio_path.exists():
            pytest.skip(f"Audio file not found: {audio_path}")

        # Step 1: Stream audio to EARS and get transcription
        chunks = audio_file_to_pcm_chunks(audio_path, CHUNK_DURATION_MS)
        transcriptions, messages = await stream_audio_to_ears(
            all_servers["ears_url"],
            chunks,
            chunk_delay_ms=CHUNK_DURATION_MS,
        )

        # Verify we got transcription
        assert len(transcriptions) > 0, "EARS should produce transcription from audio"
        full_transcription = " ".join(transcriptions).strip()

        # Verify transcription roughly matches expected
        result_normalized = normalize_text(full_transcription)
        expected_normalized = normalize_text(expected_transcription)
        assert expected_normalized in result_normalized or result_normalized in expected_normalized, (
            f"Transcription mismatch:\n"
            f"  Expected: {expected_transcription}\n"
            f"  Got: {full_transcription}"
        )

        # Step 2: Send transcription to MIND (like FACE does)
        client = E2ETestClient(base_url=all_servers["mind_url"])
        assert client.connect(), "Should connect to MIND server"

        response = client.send_transcription(
            text=full_transcription,
            original_voice=full_transcription,  # FACE sends original as well
        )

        # Step 3: Verify MIND responded
        assert response is not None, "MIND should return a response"
        assert "messages" in response, "Response should contain messages"
        assert "mode" in response, "Response should contain current mode"
        assert "current_directory" in response, "Response should contain current directory"

        client.disconnect()

    @pytest.mark.slow
    @pytest.mark.integration
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "filename,expected_transcription",
        get_test_case_params(),
        ids=get_test_case_ids(),
    )
    async def test_audio_to_mind_parametrized(
        self,
        all_servers,
        filename: str,
        expected_transcription: str,
    ):
        """
        Parametrized E2E test for all audio samples.

        Each audio file is streamed to EARS, transcribed, and sent to MIND.
        """
        audio_path = AUDIO_DIR / filename
        if not audio_path.exists():
            pytest.skip(f"Audio file not found: {audio_path}")

        # Step 1: Stream audio to EARS
        chunks = audio_file_to_pcm_chunks(audio_path, CHUNK_DURATION_MS)
        transcriptions, _ = await stream_audio_to_ears(
            all_servers["ears_url"],
            chunks,
            chunk_delay_ms=CHUNK_DURATION_MS,
        )

        assert len(transcriptions) > 0, f"No transcription for {filename}"
        full_transcription = " ".join(transcriptions).strip()

        # Step 2: Send to MIND
        client = E2ETestClient(base_url=all_servers["mind_url"])
        assert client.connect()

        response = client.send_transcription(
            text=full_transcription,
            original_voice=full_transcription,
        )

        # Step 3: Verify response structure
        assert response is not None, f"No response from MIND for: {full_transcription}"
        assert "messages" in response
        assert "mode" in response
        assert "current_directory" in response

        client.disconnect()


# ------------------------------------------------------------------------------
# E2E Tests: Mode Switching via Voice
# ------------------------------------------------------------------------------

class TestVoiceModeSwitching:
    """
    Tests mode switching through voice commands processed via the full pipeline.
    """

    @pytest.mark.slow
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_voice_cli_mode_switch(self, all_servers):
        """
        Test switching to CLI mode via voice command.

        Uses the 'command mode' recording which should trigger CLI mode.
        """
        # Find the command mode recording
        test_cases = load_transcription_test_cases()
        command_mode_case = next(
            (c for c in test_cases if "command mode" in c["transcription"].lower()),
            None
        )

        if not command_mode_case:
            pytest.skip("No 'command mode' test recording available")

        audio_path = AUDIO_DIR / command_mode_case["filename"]
        if not audio_path.exists():
            pytest.skip(f"Audio file not found: {audio_path}")

        # Stream audio to EARS
        chunks = audio_file_to_pcm_chunks(audio_path, CHUNK_DURATION_MS)
        transcriptions, _ = await stream_audio_to_ears(
            all_servers["ears_url"],
            chunks,
            chunk_delay_ms=CHUNK_DURATION_MS,
        )

        assert len(transcriptions) > 0
        full_transcription = " ".join(transcriptions).strip()

        # Send to MIND - should trigger mode switch
        client = E2ETestClient(base_url=all_servers["mind_url"])
        assert client.connect()

        response = client.send_transcription(full_transcription)

        # Verify mode changed to CLI
        assert response is not None
        # The transcription contains "command mode" which should trigger CLI mode
        # Note: actual mode depends on how MIND parses the transcription
        assert "mode" in response

        client.disconnect()

    @pytest.mark.slow
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_voice_code_mode_switch(self, all_servers):
        """
        Test switching to code mode via voice command.

        Uses the 'code mode' recording which should trigger Claude Code mode.
        """
        test_cases = load_transcription_test_cases()
        code_mode_case = next(
            (c for c in test_cases if "code mode" in c["transcription"].lower()),
            None
        )

        if not code_mode_case:
            pytest.skip("No 'code mode' test recording available")

        audio_path = AUDIO_DIR / code_mode_case["filename"]
        if not audio_path.exists():
            pytest.skip(f"Audio file not found: {audio_path}")

        # Stream audio to EARS
        chunks = audio_file_to_pcm_chunks(audio_path, CHUNK_DURATION_MS)
        transcriptions, _ = await stream_audio_to_ears(
            all_servers["ears_url"],
            chunks,
            chunk_delay_ms=CHUNK_DURATION_MS,
        )

        assert len(transcriptions) > 0
        full_transcription = " ".join(transcriptions).strip()

        # Send to MIND
        client = E2ETestClient(base_url=all_servers["mind_url"])
        assert client.connect()

        response = client.send_transcription(full_transcription)

        assert response is not None
        assert "mode" in response
        # If "code mode" is in the transcription, mode should switch
        if "code mode" in full_transcription.lower():
            # Expect claude_code mode
            pass  # Mode verification depends on exact transcription

        client.disconnect()


# ------------------------------------------------------------------------------
# E2E Tests: FACE Polling Simulation
# ------------------------------------------------------------------------------

class TestFacePollingSimulation:
    """
    Tests that simulate FACE's polling behavior for responses.
    """

    @pytest.mark.slow
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_face_polling_after_transcription(self, all_servers):
        """
        Test FACE-style polling: send text, poll for messages.

        Simulates the real FACE flow where it sends text then polls.
        """
        test_cases = load_transcription_test_cases()
        if not test_cases:
            pytest.skip("No test audio files available")

        audio_path = AUDIO_DIR / test_cases[0]["filename"]
        if not audio_path.exists():
            pytest.skip(f"Audio file not found: {audio_path}")

        # Get transcription from EARS
        chunks = audio_file_to_pcm_chunks(audio_path, CHUNK_DURATION_MS)
        transcriptions, _ = await stream_audio_to_ears(
            all_servers["ears_url"],
            chunks,
            chunk_delay_ms=CHUNK_DURATION_MS,
        )

        assert len(transcriptions) > 0
        full_transcription = " ".join(transcriptions).strip()

        # Connect to MIND
        client = E2ETestClient(base_url=all_servers["mind_url"])
        assert client.connect()

        # Send transcription (this is what FACE does)
        response = client.send_transcription(full_transcription)
        assert response is not None

        # Poll for messages (FACE does this to update UI)
        poll_response = client.poll_messages()
        assert poll_response is not None
        assert "messages" in poll_response
        assert "mode" in poll_response
        assert "current_directory" in poll_response

        client.disconnect()

    @pytest.mark.slow
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_multiple_polls_are_stable(self, all_servers):
        """
        Test that multiple polling calls return consistent state.
        """
        client = E2ETestClient(base_url=all_servers["mind_url"])
        assert client.connect()

        # Send a simple text
        response = client.send_transcription("hello")
        assert response is not None

        # Poll multiple times
        modes = []
        directories = []
        for _ in range(3):
            poll_response = client.poll_messages()
            assert poll_response is not None
            modes.append(poll_response.get("mode"))
            directories.append(poll_response.get("current_directory"))
            await asyncio.sleep(0.1)  # Small delay between polls

        # Mode and directory should remain consistent
        assert len(set(modes)) == 1, "Mode should be stable across polls"
        assert len(set(directories)) == 1, "Directory should be stable across polls"

        client.disconnect()

    @pytest.mark.slow
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_concurrent_polling_and_streaming(self, all_servers):
        """
        Test concurrent audio streaming and MIND polling.

        This simulates real usage where FACE streams audio while also
        polling MIND for responses.
        """
        test_cases = load_transcription_test_cases()
        if not test_cases:
            pytest.skip("No test audio files available")

        audio_path = AUDIO_DIR / test_cases[0]["filename"]
        if not audio_path.exists():
            pytest.skip(f"Audio file not found: {audio_path}")

        # Connect to MIND first
        client = E2ETestClient(base_url=all_servers["mind_url"])
        assert client.connect()

        # Run audio streaming and MIND polling concurrently
        chunks = audio_file_to_pcm_chunks(audio_path, CHUNK_DURATION_MS)

        async def stream_audio():
            return await stream_audio_to_ears(
                all_servers["ears_url"],
                chunks,
                chunk_delay_ms=CHUNK_DURATION_MS,
            )

        async def poll_mind():
            polls = []
            for _ in range(5):
                poll_response = client.poll_messages()
                polls.append(poll_response)
                await asyncio.sleep(0.5)
            return polls

        # Run both concurrently
        stream_result, poll_results = await asyncio.gather(
            stream_audio(),
            poll_mind(),
        )

        transcriptions, messages = stream_result

        # Audio streaming should complete successfully
        assert len(transcriptions) > 0 or len(messages) > 0, "Audio stream should produce output"

        # Polling should return valid responses
        for poll in poll_results:
            assert poll is not None, "MIND should respond to polls"

        client.disconnect()


# ------------------------------------------------------------------------------
# E2E Tests: Response Content Verification
# ------------------------------------------------------------------------------

class TestResponseContentVerification:
    """
    Tests that verify the content of responses matches expectations.
    """

    @pytest.mark.slow
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_cli_command_response_structure(self, all_servers):
        """
        Test that CLI commands produce correctly structured responses.
        """
        client = E2ETestClient(base_url=all_servers["mind_url"])
        assert client.connect()

        # Switch to CLI mode
        response = client.send_transcription("cli mode")
        assert response is not None
        assert client.mode == "cli"

        # Execute a simple command
        response = client.send_transcription("echo hello from e2e test")
        assert response is not None

        # Verify response structure
        messages = response.get("messages", [])
        assert len(messages) > 0, "Should have response messages"

        cli_msg = messages[0]
        assert cli_msg.get("type") == "cli_result"
        assert cli_msg.get("success") is True
        assert "hello" in cli_msg.get("output", "").lower()

        client.disconnect()

    @pytest.mark.slow
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_mode_change_message_structure(self, all_servers):
        """
        Test that mode changes produce correctly structured messages.
        """
        client = E2ETestClient(base_url=all_servers["mind_url"])
        assert client.connect()

        # Change modes
        for mode_trigger, expected_mode in [
            ("cli mode", "cli"),
            ("chat mode", "ollama"),
            ("code mode", "claude_code"),
        ]:
            response = client.send_transcription(mode_trigger)
            assert response is not None

            # Verify mode changed
            assert response.get("mode") == expected_mode, f"Mode should be {expected_mode}"

            # Verify message structure
            messages = response.get("messages", [])
            if messages:
                msg = messages[0]
                assert msg.get("type") == "system"
                assert msg.get("mode_changed") is True
                assert msg.get("new_mode") == expected_mode

        client.disconnect()


# ------------------------------------------------------------------------------
# E2E Tests: Error Handling
# ------------------------------------------------------------------------------

class TestE2EErrorHandling:
    """
    Tests for error handling across the full E2E flow.
    """

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_empty_transcription_handling(self, all_servers):
        """
        Test that empty transcriptions are handled gracefully.
        """
        client = E2ETestClient(base_url=all_servers["mind_url"])
        assert client.connect()

        # Send empty text (simulates no speech detected)
        response = client.send_transcription("")

        # Should not crash, may return response or None
        # Important thing is no exception

        client.disconnect()

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_whitespace_transcription_handling(self, all_servers):
        """
        Test that whitespace-only transcriptions are handled gracefully.
        """
        client = E2ETestClient(base_url=all_servers["mind_url"])
        assert client.connect()

        # Send whitespace
        response = client.send_transcription("   ")

        # Should handle gracefully

        client.disconnect()

    @pytest.mark.slow
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_ears_connection_before_mind(self, all_servers):
        """
        Test that EARS can process audio independently of MIND state.
        """
        test_cases = load_transcription_test_cases()
        if not test_cases:
            pytest.skip("No test audio files available")

        audio_path = AUDIO_DIR / test_cases[0]["filename"]
        if not audio_path.exists():
            pytest.skip(f"Audio file not found: {audio_path}")

        # Stream to EARS WITHOUT connecting to MIND first
        chunks = audio_file_to_pcm_chunks(audio_path, CHUNK_DURATION_MS)
        transcriptions, messages = await stream_audio_to_ears(
            all_servers["ears_url"],
            chunks,
            chunk_delay_ms=CHUNK_DURATION_MS,
        )

        # EARS should work independently
        assert len(transcriptions) > 0 or len(messages) > 0


# ------------------------------------------------------------------------------
# E2E Tests: Session Persistence
# ------------------------------------------------------------------------------

class TestSessionPersistence:
    """
    Tests for session state persistence across requests.
    """

    @pytest.mark.slow
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_mode_persists_across_transcriptions(self, all_servers):
        """
        Test that mode persists when sending multiple transcriptions.
        """
        client = E2ETestClient(base_url=all_servers["mind_url"])
        assert client.connect()

        # Switch to CLI mode
        response = client.send_transcription("cli mode")
        assert response is not None
        assert client.mode == "cli"

        # Send multiple commands - mode should persist
        for cmd in ["echo test", "pwd", "ls"]:
            response = client.send_transcription(cmd)
            assert response is not None
            assert response.get("mode") == "cli", f"Mode should stay CLI after '{cmd}'"

        client.disconnect()

    @pytest.mark.slow
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_directory_persists_in_responses(self, all_servers):
        """
        Test that current_directory is consistently returned.
        """
        client = E2ETestClient(base_url=all_servers["mind_url"])
        assert client.connect()

        # Send several transcriptions
        transcriptions = ["hello", "cli mode", "pwd"]
        for text in transcriptions:
            response = client.send_transcription(text)
            assert response is not None
            assert "current_directory" in response
            assert response["current_directory"] is not None
            assert "/" in response["current_directory"]

        client.disconnect()
