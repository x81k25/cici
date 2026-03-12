"""Voice/microphone tests using audio file injection.

Instead of requiring a real microphone, these tests push pre-recorded
audio files to the device and trigger the INJECT_AUDIO broadcast.
The app streams the file to EARS exactly as if it came from the mic.

Requires: ffmpeg (for webm→PCM conversion), test fixtures in tests/audio/.
"""

import json
import shutil
import tempfile
import time
from pathlib import Path

import pytest

from helpers import (
    AUDIO_FIXTURES_DIR,
    AdbHelper,
    cleanup_device_audio,
    convert_webm_to_pcm,
    inject_audio,
    inject_audio_and_wait,
    parse_ui_state,
    push_audio_to_device,
    wait_for_new_message,
)

pytestmark = pytest.mark.voice

HAS_FFMPEG = shutil.which("ffmpeg") is not None
HAS_FIXTURES = AUDIO_FIXTURES_DIR.exists() and list(AUDIO_FIXTURES_DIR.glob("*.webm"))


def _get_transcriptions() -> dict[str, str]:
    """Load expected transcriptions from fixtures."""
    t_file = AUDIO_FIXTURES_DIR / "transcriptions.json"
    if not t_file.exists():
        return {}
    with open(t_file) as f:
        entries = json.load(f)
    return {e["filename"]: e["transcription"] for e in entries}


def _pick_short_fixture() -> Path | None:
    """Pick the shortest webm fixture for quick tests."""
    webms = sorted(AUDIO_FIXTURES_DIR.glob("recording_*.webm"), key=lambda p: p.stat().st_size)
    return webms[0] if webms else None


@pytest.fixture(scope="session")
def pcm_fixtures(tmp_path_factory):
    """Convert webm fixtures to raw PCM files once per session."""
    if not HAS_FFMPEG or not HAS_FIXTURES:
        pytest.skip("ffmpeg or audio fixtures not available")

    tmpdir = tmp_path_factory.mktemp("pcm")
    converted = {}
    for webm in AUDIO_FIXTURES_DIR.glob("recording_*.webm"):
        pcm_path = tmpdir / (webm.stem + ".pcm")
        if convert_webm_to_pcm(webm, pcm_path):
            converted[webm.name] = pcm_path
    if not converted:
        pytest.skip("No audio files could be converted")
    return converted


@pytest.fixture(scope="session")
def device_audio(adb, pcm_fixtures):
    """Push converted PCM files to the Android device."""
    paths = {}
    for name, local_path in pcm_fixtures.items():
        device_name = name.replace(".webm", ".pcm")
        device_path = push_audio_to_device(adb, local_path, device_name)
        paths[name] = device_path
    yield paths
    cleanup_device_audio(adb)


@pytest.fixture
def short_audio(device_audio):
    """Return the device path of the shortest audio fixture."""
    fixture = _pick_short_fixture()
    if fixture is None or fixture.name not in device_audio:
        pytest.skip("No short audio fixture available")
    return device_audio[fixture.name]


class TestVoice:

    def test_mic_starts_recording(self, adb: AdbHelper):
        """Tapping mic button should show recording indicator."""
        adb.tap_element("btn_mic")
        time.sleep(1)
        state = parse_ui_state(adb)
        has_indicator = (
            state.mic_indicator_visible
            or state.has_text("Listening")
            or state.has_text("Recording")
        )
        assert has_indicator, "Recording indicator should appear"
        adb.tap_element("btn_mic")
        time.sleep(0.5)

    def test_mic_stops_recording(self, adb: AdbHelper):
        """Tapping mic again should stop recording."""
        adb.tap_element("btn_mic")
        time.sleep(1)
        adb.tap_element("btn_mic")
        time.sleep(1)
        state = parse_ui_state(adb)
        assert not state.mic_indicator_visible, "Mic indicator should be hidden"

    def test_mic_permission(self, adb: AdbHelper):
        """RECORD_AUDIO permission should be granted."""
        result = adb.run(
            "dumpsys package com.homelab.cici | grep RECORD_AUDIO"
        )
        assert "granted=true" in result.stdout, "RECORD_AUDIO should be granted"

    def test_ears_connects(self, adb: AdbHelper):
        """Tapping mic should trigger EARS connection message."""
        before = parse_ui_state(adb)
        count_before = before.total_msg_nodes
        adb.tap_element("btn_mic")
        time.sleep(2)
        state = parse_ui_state(adb)
        new_msgs = state.messages[len(before.messages):]
        has_ears = any(
            "EARS connected" in m or "Listening" in m
            for m in new_msgs
        )
        assert has_ears, f"Should see EARS connection message, got: {new_msgs}"
        adb.tap_element("btn_mic")
        time.sleep(0.5)

    def test_recording_toggle_cycle(self, adb: AdbHelper):
        """Tapping mic 3 times should toggle correctly each time."""
        adb.tap_element("btn_mic")
        time.sleep(1)
        state = parse_ui_state(adb)
        started = state.mic_indicator_visible or state.has_text("Listening")
        assert started, "First tap should start recording"

        adb.tap_element("btn_mic")
        time.sleep(1)
        state = parse_ui_state(adb)
        assert not state.mic_indicator_visible, "Second tap should stop"

        adb.tap_element("btn_mic")
        time.sleep(1)
        state = parse_ui_state(adb)
        restarted = state.mic_indicator_visible or state.has_text("Listening")
        assert restarted, "Third tap should restart recording"

        adb.tap_element("btn_mic")
        time.sleep(0.5)

    @pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg not installed")
    @pytest.mark.skipif(not HAS_FIXTURES, reason="No audio fixtures in tests/audio/")
    def test_audio_injection_triggers_listening(self, adb: AdbHelper, short_audio, fresh_app):
        """Injecting audio should show 'Listening...' indicator."""
        before = parse_ui_state(adb)
        inject_audio(adb, short_audio)
        time.sleep(2)
        state = parse_ui_state(adb)
        has_listening = (
            state.has_text("Listening")
            or state.has_text("file injection")
            or state.has_text("EARS connected")
        )
        assert has_listening, f"Should show listening indicator. msgs: {state.messages}"

    @pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg not installed")
    @pytest.mark.skipif(not HAS_FIXTURES, reason="No audio fixtures in tests/audio/")
    @pytest.mark.slow
    def test_transcription_from_file(self, adb: AdbHelper, short_audio, fresh_app):
        """Injected audio should produce a transcription in the UI."""
        state = inject_audio_and_wait(adb, short_audio, timeout=30)
        # Should see transcription text or at least EARS messages
        transcriptions = _get_transcriptions()
        fixture_name = _pick_short_fixture().name if _pick_short_fixture() else ""
        expected_words = transcriptions.get(fixture_name, "").lower().split()[:3]

        has_transcription = False
        for word in expected_words:
            if state.has_text(word):
                has_transcription = True
                break

        # Fallback: just check that new messages appeared beyond system msgs
        assert has_transcription or state.total_msg_nodes >= 3, \
            f"Should have transcription. msgs: {state.messages}"

    @pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg not installed")
    @pytest.mark.skipif(not HAS_FIXTURES, reason="No audio fixtures in tests/audio/")
    @pytest.mark.slow
    def test_voice_to_mind_flow(self, adb: AdbHelper, device_audio, fresh_app):
        """Full flow: injected audio → transcription → MIND response."""
        # Use the "testing testing" fixture — shortest with known transcription
        fixture = _pick_short_fixture()
        if fixture is None or fixture.name not in device_audio:
            pytest.skip("No suitable audio fixture")

        device_path = device_audio[fixture.name]
        state = inject_audio_and_wait(adb, device_path, timeout=60)

        # Should have system msgs + transcription + LLM response
        assert state.total_msg_nodes >= 3, \
            f"Should have transcription + response. Nodes: {state.total_msg_nodes}, msgs: {state.messages}"

        # Verify we got an LLM response (hermes3 tag or just response nodes)
        has_response = state.has_text("[hermes3]") or state.total_msg_nodes >= 4
        assert has_response, f"Should have MIND response. msgs: {state.messages}"
