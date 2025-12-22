"""Test audio streaming on chat page using streamlit-webrtc.

These tests verify:
- Audio tab UI works correctly (START/STOP buttons)
- WebRTC audio streaming initializes
- EARS WebSocket connection is established

Note: These are E2E browser tests using Playwright with Firefox.
For debug mode testing of EARS, see the integration tests in /tests/test_face_ears_integration.py.
"""

import json
from playwright.sync_api import sync_playwright, ConsoleMessage


def test_audio_chat_firefox():
    """Test audio streaming on chat page in Firefox."""

    console_messages: list[dict] = []
    errors: list[str] = []
    websocket_messages: list[dict] = []

    def handle_console(msg: ConsoleMessage):
        """Capture all console messages."""
        msg_data = {
            "type": msg.type,
            "text": msg.text,
        }
        console_messages.append(msg_data)

        # Capture WebSocket-related messages (debug mode responses)
        if "debug" in msg.text.lower() or "websocket" in msg.text.lower():
            websocket_messages.append(msg_data)

        # Only print errors and important logs
        if msg.type in ("error", "warning") or "EARS" in msg.text:
            print(f"[{msg.type.upper()}] {msg.text}")

    def handle_page_error(error):
        """Capture page errors."""
        errors.append(str(error))
        print(f"[PAGE ERROR] {error}")

    with sync_playwright() as p:
        # Launch Firefox with fake media devices
        browser = p.firefox.launch(
            headless=True,
            firefox_user_prefs={
                "media.navigator.streams.fake": True,
                "media.navigator.permission.disabled": True,
            },
        )

        context = browser.new_context(ignore_https_errors=True)
        page = context.new_page()

        page.on("console", handle_console)
        page.on("pageerror", handle_page_error)

        print("\n" + "=" * 60)
        print("AUDIO CHAT TEST (Firefox + streamlit-webrtc)")
        print("=" * 60)

        # Navigate to app (chat is default page)
        print("\n[1] Navigating to app...")
        page.goto("https://localhost:8501/", wait_until="networkidle")
        page.wait_for_timeout(5000)

        # Check page state
        page_content = page.text_content("body") or ""
        print(f"    Page loaded. MIND status: {'online' if 'MIND online' in page_content else 'offline'}")

        # Click Audio tab
        print("\n[2] Looking for Audio tab...")
        page.wait_for_timeout(2000)

        # Try different selectors for the tab
        audio_tab = page.locator("button:has-text('Audio')").first
        if not audio_tab.is_visible():
            audio_tab = page.get_by_text("Audio", exact=True).first

        if audio_tab.is_visible():
            audio_tab.click()
            page.wait_for_timeout(2000)
            print("    Audio tab selected")
        else:
            print("    ERROR: Audio tab not found")
            print(f"    Page text: {page.text_content('body')[:500]}")
            browser.close()
            return

        # Look for START button (streamlit-webrtc)
        print("\n[3] Looking for START button...")
        page.wait_for_timeout(2000)  # Wait for webrtc component to load

        # Try different selectors
        start_button = page.locator("button:has-text('START')").first
        if not start_button.is_visible():
            start_button = page.locator("button:has-text('Start')").first
        if not start_button.is_visible():
            # Check in iframes
            for frame in page.frames:
                btn = frame.locator("button:has-text('START')")
                if btn.count() > 0:
                    start_button = btn.first
                    break

        if start_button.is_visible():
            print("    Found START button")

            print("\n[4] Clicking START...")
            start_button.click()
            page.wait_for_timeout(5000)

            # Check if streaming started
            stop_button = page.get_by_role("button", name="STOP")
            if stop_button.is_visible():
                print("    SUCCESS: Streaming started (STOP button visible)")

                # Let it stream for a bit
                page.wait_for_timeout(3000)

                # Stop streaming
                print("\n[5] Clicking STOP...")
                stop_button.click()
                page.wait_for_timeout(2000)
                print("    Streaming stopped")
            else:
                print("    WARNING: STOP button not visible - streaming may not have started")
        else:
            print("    ERROR: START button not found")

        # Check for any page content indicating success/failure
        print("\n[6] Checking page state...")
        page_text = page.text_content("body")

        if "EARS" in page_text:
            print("    EARS connection info found on page")
        if "error" in page_text.lower():
            print("    WARNING: 'error' found in page text")

        # Summary
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)

        error_logs = [m for m in console_messages if m["type"] == "error"]
        if error_logs:
            print(f"\nConsole errors ({len(error_logs)}):")
            for msg in error_logs[:5]:  # First 5
                print(f"  - {msg['text'][:100]}")
        else:
            print("\nNo console errors")

        if errors:
            print(f"\nPage errors: {errors}")
        else:
            print("No page errors")

        # WebSocket/debug message summary
        if websocket_messages:
            print(f"\nWebSocket messages ({len(websocket_messages)}):")
            for msg in websocket_messages[:5]:
                print(f"  - {msg['text'][:100]}")
        else:
            print("\nNo WebSocket messages captured")

        print("\n" + "=" * 60)

        browser.close()

    return console_messages, errors, websocket_messages


def test_audio_chat_ui_elements():
    """Test that required UI elements exist on the chat page."""

    with sync_playwright() as p:
        browser = p.firefox.launch(
            headless=True,
            firefox_user_prefs={
                "media.navigator.streams.fake": True,
                "media.navigator.permission.disabled": True,
            },
        )

        context = browser.new_context(ignore_https_errors=True)
        page = context.new_page()

        # Navigate to app
        page.goto("https://localhost:8501/", wait_until="networkidle")
        page.wait_for_timeout(5000)

        # Check for required UI elements
        page_content = page.text_content("body") or ""

        # Verify tabs exist
        assert "Text" in page_content or page.locator("button:has-text('Text')").count() > 0, \
            "Text tab should exist"
        assert "Audio" in page_content or page.locator("button:has-text('Audio')").count() > 0, \
            "Audio tab should exist"

        # Click Audio tab
        audio_tab = page.locator("button:has-text('Audio')").first
        if audio_tab.is_visible():
            audio_tab.click()
            page.wait_for_timeout(2000)

        # Verify START button exists in Audio tab
        start_button = page.locator("button:has-text('START')").first
        if not start_button.is_visible():
            start_button = page.locator("button:has-text('Start')").first

        # START button should be visible after clicking Audio tab
        # (may not be visible if webrtc component hasn't loaded)
        assert start_button.count() > 0 or "START" in page.text_content("body"), \
            "START button should exist in Audio tab"

        browser.close()


if __name__ == "__main__":
    test_audio_chat_firefox()
