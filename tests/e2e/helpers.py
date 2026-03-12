"""
E2E test helpers: ADB wrapper, UI state parser, polling utilities.
"""

import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BACKEND_HOST = "192.168.50.2"
MIND_PORT = 30211
EARS_PORT = 30212
MOUTH_PORT = 30213
APP_PACKAGE = "com.homelab.cici"
APP_ACTIVITY = f"{APP_PACKAGE}/.MainActivity"

LLM_RESPONSE_TIMEOUT = 45  # seconds — LLM inference can be slow
MODE_SWITCH_TIMEOUT = 10
POLL_INTERVAL = 1.5

UI_DUMP_PATH = "/sdcard/window_dump.xml"


# ---------------------------------------------------------------------------
# AdbHelper
# ---------------------------------------------------------------------------

class AdbHelper:
    """Wraps ADB shell operations via subprocess."""

    def run(self, cmd: str, timeout: int = 15) -> subprocess.CompletedProcess:
        """Run an adb shell command."""
        return subprocess.run(
            ["adb", "shell", cmd],
            capture_output=True, text=True, timeout=timeout,
        )

    def run_host(self, args: list[str], timeout: int = 15) -> subprocess.CompletedProcess:
        """Run an adb command on the host (not shell)."""
        return subprocess.run(
            ["adb"] + args,
            capture_output=True, text=True, timeout=timeout,
        )

    def is_device_connected(self) -> bool:
        result = subprocess.run(
            ["adb", "devices"], capture_output=True, text=True, timeout=5,
        )
        lines = [l for l in result.stdout.strip().split("\n")[1:] if l.strip()]
        return any("device" in l for l in lines)

    def launch_app(self):
        self.run(f"am start -n {APP_ACTIVITY}")
        time.sleep(2)

    def force_stop_app(self):
        self.run(f"am force-stop {APP_PACKAGE}")
        time.sleep(0.5)

    def clear_app_data(self):
        self.run(f"pm clear {APP_PACKAGE}")
        time.sleep(1)

    def grant_mic_permission(self):
        self.run(f"pm grant {APP_PACKAGE} android.permission.RECORD_AUDIO")

    def is_app_foreground(self) -> bool:
        result = self.run("dumpsys activity activities | grep mFocusedApp")
        return APP_PACKAGE in result.stdout

    def is_app_installed(self) -> bool:
        result = self.run(f"pm list packages {APP_PACKAGE}")
        return APP_PACKAGE in result.stdout

    def type_text(self, text: str):
        """Type text via ADB input. Replaces spaces with %s."""
        escaped = text.replace(" ", "%s")
        # Escape shell-special characters
        escaped = escaped.replace("'", "\\'")
        escaped = escaped.replace('"', '\\"')
        escaped = escaped.replace("&", "\\&")
        escaped = escaped.replace("|", "\\|")
        escaped = escaped.replace(";", "\\;")
        escaped = escaped.replace("(", "\\(")
        escaped = escaped.replace(")", "\\)")
        self.run(f"input text '{escaped}'")

    def press_enter(self):
        self.run("input keyevent 66")

    def tap(self, x: int, y: int):
        self.run(f"input tap {x} {y}")

    def dump_ui(self) -> str:
        """Run uiautomator dump and return the XML."""
        self.run(f"uiautomator dump {UI_DUMP_PATH}")
        result = self.run(f"cat {UI_DUMP_PATH}")
        return result.stdout

    def get_ui_texts(self) -> list[str]:
        """Extract all text= values from uiautomator XML."""
        xml = self.dump_ui()
        return re.findall(r'text="([^"]*)"', xml)

    def get_element_bounds(self, resource_id: str) -> tuple[int, int, int, int] | None:
        """Parse bounds attribute for a resource-id from uiautomator XML."""
        xml = self.dump_ui()
        full_id = f"{APP_PACKAGE}:id/{resource_id}"
        # Find the full <node .../> with this resource-id
        node_pattern = rf'<node\s[^>]*resource-id="{re.escape(full_id)}"[^>]*/>'
        node_match = re.search(node_pattern, xml)
        if not node_match:
            return None
        node = node_match.group(0)
        bounds_match = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', node)
        if not bounds_match:
            return None
        return (int(bounds_match.group(1)), int(bounds_match.group(2)),
                int(bounds_match.group(3)), int(bounds_match.group(4)))

    def tap_element(self, resource_id: str) -> bool:
        """Tap the center of an element by resource-id."""
        bounds = self.get_element_bounds(resource_id)
        if bounds is None:
            return False
        x = (bounds[0] + bounds[2]) // 2
        y = (bounds[1] + bounds[3]) // 2
        self.tap(x, y)
        return True

    def get_logcat(self, lines: int = 200) -> str:
        result = self.run(f"logcat -d -t {lines}")
        return result.stdout

    def clear_logcat(self):
        self.run("logcat -c")


# ---------------------------------------------------------------------------
# UIState
# ---------------------------------------------------------------------------

@dataclass
class UIState:
    """Parsed state from uiautomator XML dump."""
    raw_xml: str
    texts: list[str] = field(default_factory=list)
    status_bar_text: str = ""
    messages: list[str] = field(default_factory=list)
    total_msg_nodes: int = 0  # all msg_content nodes, including empty (recycled)
    mic_indicator_visible: bool = False

    @property
    def last_message(self) -> str | None:
        return self.messages[-1] if self.messages else None

    def has_text(self, substring: str) -> bool:
        """Case-insensitive search across all UI text."""
        lower = substring.lower()
        return any(lower in t.lower() for t in self.texts)

    @property
    def mind_status(self) -> str:
        m = re.search(r"MIND:(\w+)", self.status_bar_text)
        return m.group(1) if m else "UNKNOWN"

    @property
    def mouth_status(self) -> str:
        m = re.search(r"MOUTH:(\w+)", self.status_bar_text)
        return m.group(1) if m else "UNKNOWN"

    @property
    def current_mode(self) -> str:
        m = re.search(r"Mode:\s*(\w+)", self.status_bar_text)
        return m.group(1) if m else ""

    @property
    def message_count(self) -> int:
        return len(self.messages)


def _extract_attr_from_node(xml: str, resource_id: str, attr: str) -> str | None:
    """Find a <node> by resource-id and extract an attribute value.

    Handles any attribute ordering within the node.
    """
    # Find full <node .../> element containing this resource-id
    full_id = f"{APP_PACKAGE}:id/{resource_id}"
    pattern = rf'<node\s[^>]*resource-id="{re.escape(full_id)}"[^>]*/>'
    match = re.search(pattern, xml)
    if not match:
        return None
    node = match.group(0)
    attr_match = re.search(rf'{attr}="([^"]*)"', node)
    return attr_match.group(1) if attr_match else None


def _find_nodes_by_resource_id(xml: str, resource_id: str) -> list[str]:
    """Return all <node .../> elements with the given resource-id."""
    full_id = f"{APP_PACKAGE}:id/{resource_id}"
    pattern = rf'<node\s[^>]*resource-id="{re.escape(full_id)}"[^>]*/>'
    return re.findall(pattern, xml)


def parse_ui_state(adb: AdbHelper) -> UIState:
    """Dump UI and parse into UIState."""
    xml = adb.dump_ui()
    texts = re.findall(r'text="([^"]*)"', xml)

    # Status bar text
    status_text = _extract_attr_from_node(xml, "status_bar", "text") or ""

    # Mic indicator visibility
    mic_visible = False
    mic_node = _extract_attr_from_node(xml, "mic_indicator", "bounds")
    if mic_node:
        bounds = re.search(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', mic_node)
        if bounds:
            y1, y2 = int(bounds.group(2)), int(bounds.group(4))
            mic_visible = y2 > y1

    # Messages: extract text from all msg_content nodes
    msg_nodes = _find_nodes_by_resource_id(xml, "msg_content")
    messages = []
    for node in msg_nodes:
        text_match = re.search(r'text="([^"]*)"', node)
        if text_match and text_match.group(1):
            messages.append(text_match.group(1))

    return UIState(
        raw_xml=xml,
        texts=texts,
        status_bar_text=status_text,
        messages=messages,
        total_msg_nodes=len(msg_nodes),
        mic_indicator_visible=mic_visible,
    )


# ---------------------------------------------------------------------------
# Polling helpers
# ---------------------------------------------------------------------------

def send_text_via_adb(adb: AdbHelper, text: str):
    """Type text into the input field and tap send."""
    adb.tap_element("text_input")
    time.sleep(0.3)
    adb.type_text(text)
    time.sleep(0.3)
    adb.tap_element("btn_send")


def wait_for_new_message(
    adb: AdbHelper,
    previous_node_count: int,
    timeout: float = LLM_RESPONSE_TIMEOUT,
) -> UIState:
    """Poll UI until total msg node count exceeds previous_node_count.

    Uses total_msg_nodes (includes recycled empty nodes) rather than
    message_count (text-only) because RecyclerView recycles off-screen
    items, clearing their text attribute.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        state = parse_ui_state(adb)
        if state.total_msg_nodes > previous_node_count:
            return state
        time.sleep(POLL_INTERVAL)
    return parse_ui_state(adb)


def send_and_wait(
    adb: AdbHelper,
    text: str,
    timeout: float = LLM_RESPONSE_TIMEOUT,
) -> UIState:
    """Send text via ADB and wait for at least one response beyond the user msg."""
    before = parse_ui_state(adb)
    nodes_before = before.total_msg_nodes
    send_text_via_adb(adb, text)
    time.sleep(0.5)
    # user msg + at least one response = nodes_before + 2
    return wait_for_new_message(adb, nodes_before + 1, timeout)


def send_and_wait_for_mode(
    adb: AdbHelper,
    text: str,
    timeout: float = MODE_SWITCH_TIMEOUT,
) -> UIState:
    """Send a mode-switch command and wait for the system message."""
    before = parse_ui_state(adb)
    nodes_before = before.total_msg_nodes
    send_text_via_adb(adb, text)
    time.sleep(0.5)
    return wait_for_new_message(adb, nodes_before + 1, timeout)


# ---------------------------------------------------------------------------
# Audio injection helpers
# ---------------------------------------------------------------------------

DEVICE_AUDIO_DIR = f"/data/user/0/{APP_PACKAGE}/files/test-audio"
DEVICE_TMP_DIR = "/data/local/tmp"
ACTION_INJECT_AUDIO = "com.homelab.cici.INJECT_AUDIO"

# Path to tests/audio/ relative to this file
AUDIO_FIXTURES_DIR = Path(__file__).parent.parent / "audio"


def convert_webm_to_pcm(webm_path: Path, pcm_path: Path) -> bool:
    """Convert a webm audio file to raw PCM (16kHz, mono, int16) using ffmpeg."""
    if not shutil.which("ffmpeg"):
        return False
    result = subprocess.run(
        ["ffmpeg", "-y", "-i", str(webm_path),
         "-ar", "16000", "-ac", "1", "-f", "s16le", str(pcm_path)],
        capture_output=True, timeout=30,
    )
    return result.returncode == 0


def push_audio_to_device(adb: AdbHelper, local_path: Path, device_filename: str) -> str:
    """Push an audio file to the app's internal storage via run-as.

    Scoped storage prevents the app from reading /sdcard/, so we push to
    /data/local/tmp first, then copy into the app's files dir with run-as.
    """
    # Ensure the target directory exists inside the app's sandbox
    subprocess.run(
        ["adb", "shell", "run-as", APP_PACKAGE, "mkdir", "-p", "files/test-audio"],
        capture_output=True, timeout=10,
    )
    # Push to a world-readable tmp location first
    tmp_path = f"{DEVICE_TMP_DIR}/{device_filename}"
    subprocess.run(
        ["adb", "push", str(local_path), tmp_path],
        capture_output=True, timeout=30,
    )
    # Copy into the app's internal storage
    device_path = f"{DEVICE_AUDIO_DIR}/{device_filename}"
    subprocess.run(
        ["adb", "shell", "run-as", APP_PACKAGE,
         "cp", tmp_path, f"files/test-audio/{device_filename}"],
        capture_output=True, timeout=10,
    )
    # Clean up tmp
    subprocess.run(
        ["adb", "shell", "rm", "-f", tmp_path],
        capture_output=True, timeout=5,
    )
    return device_path


def inject_audio(adb: AdbHelper, device_audio_path: str):
    """Send INJECT_AUDIO broadcast to the app with the given file path.

    Uses implicit broadcast (no -n flag) because the receiver is registered
    dynamically in MainActivity, not declared in the manifest.
    """
    adb.run(
        f"am broadcast -a {ACTION_INJECT_AUDIO} "
        f"--es audio_path {device_audio_path}"
    )


def inject_audio_and_wait(
    adb: AdbHelper,
    device_audio_path: str,
    timeout: float = LLM_RESPONSE_TIMEOUT,
) -> UIState:
    """Inject audio file and wait for transcription + response to appear."""
    before = parse_ui_state(adb)
    nodes_before = before.total_msg_nodes
    inject_audio(adb, device_audio_path)
    # Wait for: "Listening..." + "EARS connected" + transcription + response
    return wait_for_new_message(adb, nodes_before + 2, timeout)


def cleanup_device_audio(adb: AdbHelper):
    """Remove test audio files from the device."""
    subprocess.run(
        ["adb", "shell", "run-as", APP_PACKAGE, "rm", "-rf", "files/test-audio"],
        capture_output=True, timeout=10,
    )
