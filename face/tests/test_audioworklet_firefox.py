"""Diagnostic test for AudioWorklet in Firefox.

This test captures console logs and errors when attempting to use AudioWorklet
in Firefox to help debug compatibility issues.
"""

import re
from playwright.sync_api import sync_playwright, ConsoleMessage


def test_audioworklet_firefox_diagnostic():
    """Capture Firefox console output when loading AudioWorklet."""

    console_messages: list[dict] = []
    errors: list[str] = []

    def handle_console(msg: ConsoleMessage):
        """Capture all console messages."""
        console_messages.append({
            "type": msg.type,
            "text": msg.text,
            "location": msg.location,
        })
        print(f"[{msg.type.upper()}] {msg.text}")

    def handle_page_error(error):
        """Capture page errors."""
        errors.append(str(error))
        print(f"[PAGE ERROR] {error}")

    with sync_playwright() as p:
        # Launch Firefox with settings for audio testing
        browser = p.firefox.launch(
            headless=True,
            firefox_user_prefs={
                # Enable AudioWorklet
                "dom.audioworklet.enabled": True,
                # Allow insecure localhost
                "network.stricttransportsecurity.preloadlist": False,
                # Fake media devices for testing
                "media.navigator.streams.fake": True,
                "media.navigator.permission.disabled": True,
            },
        )

        # Create context that ignores HTTPS errors (self-signed cert)
        # Note: Firefox handles permissions via firefox_user_prefs, not permissions list
        context = browser.new_context(
            ignore_https_errors=True,
        )

        page = context.new_page()

        # Attach console and error handlers
        page.on("console", handle_console)
        page.on("pageerror", handle_page_error)

        print("\n" + "=" * 60)
        print("FIREFOX AUDIOWORKLET DIAGNOSTIC TEST")
        print("=" * 60)

        # Navigate to the testing page
        print("\n[1] Navigating to testing page...")
        page.goto("https://localhost:8501/testing", wait_until="networkidle")

        # Wait for page to fully load
        page.wait_for_timeout(3000)

        # Select Benchmark 2 (WebSocket Streaming)
        print("\n[2] Selecting Benchmark 2: WebSocket Streaming...")
        dropdown = page.locator("select").first
        if dropdown.is_visible():
            dropdown.select_option(label="Benchmark 2: WebSocket Streaming")
            page.wait_for_timeout(3000)  # Wait for iframe to load

        # Look for the Start Streaming button in the iframe
        print("\n[3] Looking for Start Streaming button...")

        # Streamlit components are in iframes
        frames = page.frames
        print(f"    Found {len(frames)} frames")

        start_button = None
        for i, frame in enumerate(frames):
            try:
                btn = frame.locator("#startBtn")
                if btn.count() > 0:
                    start_button = btn
                    print(f"    Found startBtn in frame {i}")
                    break
            except Exception as e:
                pass

        if start_button:
            # Check if button is disabled (AudioWorklet not supported)
            is_disabled = start_button.is_disabled()
            print(f"\n[4] Start button disabled: {is_disabled}")

            if is_disabled:
                # Get error message
                for frame in frames:
                    try:
                        error_el = frame.locator("#errorMsg")
                        if error_el.count() > 0:
                            error_text = error_el.text_content()
                            if error_text:
                                print(f"    Error message: {error_text}")
                    except:
                        pass
            else:
                print("\n[5] Clicking Start Streaming...")
                start_button.click()
                page.wait_for_timeout(3000)

                # Check for errors after clicking
                for frame in frames:
                    try:
                        error_el = frame.locator("#errorMsg")
                        if error_el.count() > 0:
                            error_text = error_el.text_content()
                            if error_text:
                                print(f"    Error after click: {error_text}")
                    except:
                        pass
        else:
            print("\n[4] Could not find Start Streaming button")

        # Print summary
        print("\n" + "=" * 60)
        print("CONSOLE SUMMARY")
        print("=" * 60)

        error_logs = [m for m in console_messages if m["type"] in ("error", "warning")]
        if error_logs:
            print(f"\nFound {len(error_logs)} errors/warnings:")
            for msg in error_logs:
                print(f"  [{msg['type'].upper()}] {msg['text']}")
        else:
            print("\nNo console errors or warnings captured.")

        if errors:
            print(f"\nPage errors: {errors}")

        print("\n" + "=" * 60)

        browser.close()

    return console_messages, errors


if __name__ == "__main__":
    test_audioworklet_firefox_diagnostic()
