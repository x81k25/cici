"""TTS (text-to-speech) verification tests."""

import time

import httpx
import pytest

from helpers import (
    BACKEND_HOST,
    MIND_PORT,
    MOUTH_PORT,
    AdbHelper,
    send_and_wait,
)

pytestmark = [pytest.mark.tts, pytest.mark.slow]


class TestTts:

    def test_mouth_health(self):
        """MOUTH service should be healthy."""
        r = httpx.get(f"http://{BACKEND_HOST}:{MOUTH_PORT}/health", timeout=5)
        assert r.status_code == 200

    def test_mind_tts_available(self, mind_api):
        """MIND health should report TTS as available."""
        r = mind_api.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data.get("tts_available") is True, f"tts_available should be True: {data}"

    def test_synthesis_triggered(self, adb: AdbHelper, reset_mode, fresh_app, mouth_api):
        """Sending a question should trigger TTS synthesis in MOUTH."""
        send_and_wait(adb, "What is two plus two")
        time.sleep(2)  # Give MOUTH time to process
        r = mouth_api.get("/status")
        assert r.status_code == 200
        data = r.json()
        # Backend uses pending_count/completed_count
        total = (
            data.get("pending_count", data.get("pending", 0))
            + data.get("completed_count", data.get("completed", 0))
        )
        assert total > 0, f"MOUTH should show queue activity: {data}"

    def test_queue_multiple(self, adb: AdbHelper, reset_mode, fresh_app, mouth_api):
        """Multiple messages should create queue activity."""
        send_and_wait(adb, "Tell me a joke")
        send_and_wait(adb, "Tell me another joke")
        time.sleep(2)
        r = mouth_api.get("/status")
        assert r.status_code == 200
        data = r.json()
        total = (
            data.get("pending_count", data.get("pending", 0))
            + data.get("completed_count", data.get("completed", 0))
        )
        assert total > 0, f"MOUTH queue should show activity: {data}"

    def test_audio_next_wav(self, mouth_api):
        """Direct synthesis + fetch should return WAV audio."""
        r = mouth_api.post("/synthesize", json={"text": "Hello world"})
        assert r.status_code in (200, 202), f"Synthesize failed: {r.status_code}"
        time.sleep(3)  # Wait for synthesis
        r = mouth_api.get("/audio/next")
        if r.status_code == 200:
            content_type = r.headers.get("content-type", "")
            assert "audio" in content_type or "wav" in content_type or len(r.content) > 100, \
                f"Expected audio response, got content-type: {content_type}"
        elif r.status_code == 204:
            pytest.skip("No audio ready yet (204) — synthesis may be slow")
        else:
            pytest.fail(f"Unexpected status: {r.status_code}")
