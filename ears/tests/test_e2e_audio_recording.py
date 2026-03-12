# standard library imports
import asyncio
import json
import multiprocessing
import re
import time
from pathlib import Path

# 3rd-party imports
import pydub
import pytest
import websockets

# local imports
from ears.normalize import normalize_transcription


# ------------------------------------------------------------------------------
# constants
# ------------------------------------------------------------------------------

AUDIO_DIR = Path(__file__).parent.parent.parent / "tests" / "audio"
SERVER_HOST = "localhost"
SERVER_PORT = 18766  # use non-standard port for testing
CHUNK_DURATION_MS = 100  # send audio in 100ms chunks (realistic streaming)


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
    # load audio file (pydub handles format detection)
    audio = pydub.AudioSegment.from_file(file_path)

    # convert to required format: 16kHz, mono, 16-bit
    audio = audio.set_frame_rate(16000).set_channels(1).set_sample_width(2)

    # get raw PCM bytes
    raw_pcm = audio.raw_data

    # calculate chunk size in bytes
    # 16kHz * 2 bytes per sample * (chunk_duration_ms / 1000)
    bytes_per_ms = 16000 * 2 / 1000
    chunk_size = int(bytes_per_ms * chunk_duration_ms)

    # split into chunks
    chunks = []
    for i in range(0, len(raw_pcm), chunk_size):
        chunks.append(raw_pcm[i:i + chunk_size])

    return chunks


# ------------------------------------------------------------------------------
# server management
# ------------------------------------------------------------------------------

def run_server_process(host: str, port: int, ready_event: multiprocessing.Event):
    """Run the EARS server in a subprocess."""
    import asyncio
    from ears.main import main

    async def server_main():
        # signal that we're starting
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
    ready_event.wait(timeout=10)
    time.sleep(1)  # give server a moment to fully initialize

    yield f"ws://{SERVER_HOST}:{SERVER_PORT}"

    # shutdown
    server_process.terminate()
    server_process.join(timeout=5)
    if server_process.is_alive():
        server_process.kill()


# ------------------------------------------------------------------------------
# test data loading
# ------------------------------------------------------------------------------

@pytest.fixture
def transcription_test_cases() -> list[dict]:
    """Load transcription test cases from JSON file."""
    transcriptions_file = AUDIO_DIR / "transcriptions.json"
    if not transcriptions_file.exists():
        pytest.skip(f"Transcriptions file not found: {transcriptions_file}")

    with open(transcriptions_file, "r") as f:
        return json.load(f)


def get_audio_test_ids() -> list[str]:
    """Get test IDs for parametrization."""
    transcriptions_file = AUDIO_DIR / "transcriptions.json"
    if not transcriptions_file.exists():
        return []

    with open(transcriptions_file, "r") as f:
        cases = json.load(f)
        return [case["filename"] for case in cases]


def get_audio_test_cases() -> list[tuple[str, str]]:
    """Get (filename, expected_transcription) tuples for parametrization."""
    transcriptions_file = AUDIO_DIR / "transcriptions.json"
    if not transcriptions_file.exists():
        return []

    with open(transcriptions_file, "r") as f:
        cases = json.load(f)
        return [(case["filename"], case["transcription"]) for case in cases]


# ------------------------------------------------------------------------------
# end-to-end transcription tests
# ------------------------------------------------------------------------------

class TestE2EWebSocketTranscription:
    """End-to-end tests streaming real audio through the WebSocket server."""

    @pytest.mark.slow
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "filename,expected_transcription",
        get_audio_test_cases(),
        ids=get_audio_test_ids(),
    )
    async def test_stream_audio_file(
        self,
        ears_server: str,
        filename: str,
        expected_transcription: str,
    ):
        """Stream audio file through WebSocket and verify transcription."""
        audio_path = AUDIO_DIR / filename
        if not audio_path.exists():
            pytest.skip(f"Audio file not found: {audio_path}")

        # convert to PCM chunks
        chunks = audio_file_to_pcm_chunks(audio_path, CHUNK_DURATION_MS)

        transcriptions = []
        transcription_received = asyncio.Event()

        async with websockets.connect(ears_server) as ws:
            # start a task to collect responses
            async def collect_responses():
                try:
                    async for message in ws:
                        data = json.loads(message)
                        if data.get("type") == "transcription":
                            transcriptions.append(data.get("text", ""))
                            transcription_received.set()
                except websockets.ConnectionClosed:
                    pass

            collector = asyncio.create_task(collect_responses())

            # stream audio chunks with realistic timing
            for chunk in chunks:
                await ws.send(chunk)
                await asyncio.sleep(CHUNK_DURATION_MS / 1000)  # simulate real-time

            # send silence to trigger final transcription (VAD needs silence to finalize)
            silence = b"\x00" * (16000 * 2)  # 1 second of silence
            await ws.send(silence)

            # wait for transcription (Whisper can take a few seconds)
            try:
                await asyncio.wait_for(transcription_received.wait(), timeout=30.0)
            except asyncio.TimeoutError:
                pass  # will fail assertion below

            # close connection and wait for collector
            await ws.close()
            collector.cancel()
            try:
                await collector
            except asyncio.CancelledError:
                pass

        # combine all transcriptions
        full_transcription = " ".join(transcriptions).strip()

        # verify we got something
        assert len(transcriptions) > 0, f"No transcriptions received for {filename}"

        # normalize for comparison (lowercase, remove punctuation, collapse whitespace, apply aliases)
        def normalize(text: str) -> str:
            text = normalize_transcription(text)  # apply word aliases
            text = text.lower()
            text = re.sub(r'[^\w\s]', '', text)  # remove punctuation
            text = re.sub(r'\s+', ' ', text).strip()  # collapse whitespace
            return text

        result_normalized = normalize(full_transcription)
        expected_normalized = normalize(expected_transcription)

        # check transcription matches (allowing for variations)
        assert expected_normalized in result_normalized or result_normalized in expected_normalized, (
            f"Transcription mismatch for {filename}:\n"
            f"  Expected: {expected_transcription}\n"
            f"  Got: {full_transcription}\n"
            f"  Normalized expected: {expected_normalized}\n"
            f"  Normalized got: {result_normalized}"
        )


class TestAudioFileLoading:
    """Tests for audio file loading and format handling."""

    def test_transcriptions_json_valid(self, transcription_test_cases: list[dict]):
        """Test that transcriptions.json has valid structure."""
        assert len(transcription_test_cases) > 0, "No test cases defined"

        for case in transcription_test_cases:
            assert "filename" in case, "Test case missing 'filename'"
            assert "transcription" in case, "Test case missing 'transcription'"
            assert isinstance(case["filename"], str), "filename should be string"
            assert isinstance(case["transcription"], str), "transcription should be string"

    def test_audio_files_exist(self, transcription_test_cases: list[dict]):
        """Test that all referenced audio files exist."""
        missing_files = []

        for case in transcription_test_cases:
            audio_path = AUDIO_DIR / case["filename"]
            if not audio_path.exists():
                missing_files.append(case["filename"])

        assert len(missing_files) == 0, f"Missing audio files: {missing_files}"

    def test_audio_file_converts_to_pcm(self, transcription_test_cases: list[dict]):
        """Test that audio files can be converted to PCM chunks."""
        for case in transcription_test_cases:
            audio_path = AUDIO_DIR / case["filename"]
            if not audio_path.exists():
                continue

            chunks = audio_file_to_pcm_chunks(audio_path)

            assert len(chunks) > 0, f"No chunks generated for {case['filename']}"
            # each chunk should be bytes
            for chunk in chunks:
                assert isinstance(chunk, bytes), "Chunk should be bytes"


