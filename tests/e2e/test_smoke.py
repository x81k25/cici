"""Smoke tests: device connectivity, app launch, backend health."""

import httpx
import pytest

from helpers import (
    APP_PACKAGE,
    BACKEND_HOST,
    EARS_PORT,
    MIND_PORT,
    MOUTH_PORT,
    AdbHelper,
    parse_ui_state,
    send_text_via_adb,
)

pytestmark = pytest.mark.smoke


class TestSmoke:

    def test_adb_device_connected(self, adb: AdbHelper):
        assert adb.is_device_connected()

    def test_app_installed(self, adb: AdbHelper):
        assert adb.is_app_installed()

    def test_app_launches(self, adb: AdbHelper):
        adb.force_stop_app()
        adb.launch_app()
        state = parse_ui_state(adb)
        assert state.status_bar_text, "Status bar should have text after launch"

    def test_mind_health(self):
        r = httpx.get(f"http://{BACKEND_HOST}:{MIND_PORT}/health", timeout=5)
        assert r.status_code == 200

    def test_mouth_health(self):
        r = httpx.get(f"http://{BACKEND_HOST}:{MOUTH_PORT}/health", timeout=5)
        assert r.status_code == 200

    def test_device_reaches_backend(self, adb: AdbHelper):
        """Verify the Android device can reach backend ports via nc."""
        for port in [MIND_PORT, EARS_PORT, MOUTH_PORT]:
            result = adb.run(
                f"nc -z -w 3 {BACKEND_HOST} {port} && echo OPEN || echo CLOSED"
            )
            assert "OPEN" in result.stdout, f"Port {port} not reachable from device"

    def test_status_bar_healthy(self, adb: AdbHelper, fresh_app):
        """After fresh launch, status bar should show MIND:OK and MOUTH:OK."""
        import time
        # Give health check time to complete
        time.sleep(3)
        state = parse_ui_state(adb)
        assert "MIND:OK" in state.status_bar_text
        assert "MOUTH:OK" in state.status_bar_text

    def test_can_type_text(self, adb: AdbHelper):
        """Verify we can type into the text input field."""
        adb.tap_element("text_input")
        import time
        time.sleep(0.3)
        adb.type_text("hello")
        time.sleep(0.3)
        state = parse_ui_state(adb)
        assert state.has_text("hello"), "Typed text should appear in input field"
        # Clear input by selecting all + delete
        adb.run("input keyevent 67 67 67 67 67")  # backspace x5
