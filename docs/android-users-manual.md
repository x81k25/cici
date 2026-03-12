# Android ADB Testing & Troubleshooting Manual

Reference for building, deploying, and debugging the CICI Android app (`face-android/`) via ADB.

---

## Prerequisites

- Rooted Android device with USB debugging enabled
- ADB installed on the host machine
- Android SDK (command-line tools, platform 36, build-tools 36.0.0)
  - SDK location: `~/Android/Sdk`
  - Set via `face-android/local.properties`: `sdk.dir=/home/x81k25/Android/Sdk`
- Backend services running and accessible:
  - MIND: `http://192.168.50.2:30211`
  - EARS: `ws://192.168.50.2:30212`
  - MOUTH: `http://192.168.50.2:30213`

### SDK Setup (one-time)

```bash
# Download command-line tools
mkdir -p ~/Android/Sdk && cd ~/Android/Sdk
curl -sL https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip -o cmdline-tools.zip
unzip -qo cmdline-tools.zip
mkdir -p cmdline-tools/latest
mv cmdline-tools/bin cmdline-tools/lib cmdline-tools/NOTICE.txt cmdline-tools/source.properties cmdline-tools/latest/

# Install platform and build tools
yes | ~/Android/Sdk/cmdline-tools/latest/bin/sdkmanager --sdk_root=~/Android/Sdk \
  "platforms;android-36" "build-tools;36.0.0"

# Set local.properties
echo "sdk.dir=$HOME/Android/Sdk" > /infra/ai-ml/cici/face-android/local.properties
```

---

## Build & Deploy

### Build debug APK

```bash
cd /infra/ai-ml/cici/face-android
./gradlew assembleDebug
```

Output: `app/build/outputs/apk/debug/app-debug.apk`

### Install on device

```bash
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

### Launch the app

```bash
adb shell am start -n com.homelab.cici/.MainActivity
```

### Open settings screen

```bash
adb shell am start -n com.homelab.cici/.SettingsActivity
```

### Uninstall

```bash
adb uninstall com.homelab.cici
```

---

## Device Verification

### Confirm device connection

```bash
adb devices
```

### Device info

```bash
adb shell getprop ro.product.model        # Device model
adb shell getprop ro.build.version.release # Android version
```

### Confirm app is installed

```bash
adb shell dumpsys package com.homelab.cici | grep -E "versionName|versionCode|firstInstallTime"
```

### Confirm app is in foreground

```bash
adb shell dumpsys activity activities | grep mFocusedApp
```

---

## Debugging

### Logcat (primary debugging tool)

```bash
# All logs from the app (live stream)
adb logcat --pid=$(adb shell pidof com.homelab.cici)

# Recent logs (buffered, non-blocking)
adb logcat -d -t 100 --pid=$(adb shell pidof com.homelab.cici)

# Filter by tag (if custom tags are added to Java source)
adb logcat -s "MindClient:*" "EarsClient:*" "MouthClient:*"

# Crash logs only
adb logcat -d -t 200 | grep -E "FATAL|AndroidRuntime|com.homelab.cici"
```

### Screenshots

```bash
# Capture to host
adb exec-out screencap -p > /tmp/cici-screenshot.png

# Useful for verifying UI state in headless/remote sessions
```

### Screen recording

```bash
# Record up to 30 seconds
adb shell screenrecord /sdcard/cici-test.mp4 --time-limit 30

# Pull recording to host
adb pull /sdcard/cici-test.mp4 /tmp/
```

### Permissions

```bash
# List app permissions
adb shell dumpsys package com.homelab.cici | grep "permission"

# Grant microphone permission (required for voice input)
adb shell pm grant com.homelab.cici android.permission.RECORD_AUDIO
```

---

## Network Troubleshooting

### Verify backend health from host

```bash
curl -s -o /dev/null -w "%{http_code}" http://192.168.50.2:30211/health  # MIND
curl -s -o /dev/null -w "%{http_code}" http://192.168.50.2:30213/health  # MOUTH
```

### Test connectivity from device

The device does not have `curl`. Use `nc` or `ping`:

```bash
# Ping (verifies L3 connectivity)
adb shell ping -c 3 192.168.50.2

# Check if specific ports are reachable
adb shell "nc -z -w 3 192.168.50.2 30211 && echo 'MIND OPEN' || echo 'MIND CLOSED'"
adb shell "nc -z -w 3 192.168.50.2 30212 && echo 'EARS OPEN' || echo 'EARS CLOSED'"
adb shell "nc -z -w 3 192.168.50.2 30213 && echo 'MOUTH OPEN' || echo 'MOUTH CLOSED'"

# Check WiFi state
adb shell dumpsys wifi | grep "mNetworkInfo"
```

Note: `/dev/tcp` does not work on Android's shell — use `nc` instead.

### Port forwarding (if device can't reach host network directly)

```bash
# Forward device localhost:30211 → host 192.168.50.2:30211
adb reverse tcp:30211 tcp:30211
adb reverse tcp:30212 tcp:30212
adb reverse tcp:30213 tcp:30213
```

This allows the app to connect to `localhost:<port>` on the device, which ADB tunnels to the host. Requires updating the app's settings to use `127.0.0.1` instead of `192.168.50.2`.

---

## UI Interaction via ADB

### Tap at coordinates

```bash
adb shell input tap <x> <y>
```

Use a screenshot to identify coordinates. Note: `screencap` returns native resolution (e.g., 1080x2400).

### Type text

```bash
adb shell input text "hello%scici"   # %s = space
```

### Press keys

```bash
adb shell input keyevent KEYCODE_ENTER
adb shell input keyevent KEYCODE_BACK
adb shell input keyevent KEYCODE_HOME
```

### Swipe

```bash
adb shell input swipe <x1> <y1> <x2> <y2> <duration_ms>
```

---

## Common Issues

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| App installs but shows black screen | Dark theme + no data loaded yet | Use `uiautomator dump` to read UI text (see below) |
| "Connection refused" in logcat | Backend service down or wrong IP/port | Verify health endpoints; check app settings |
| `MOUTH poll error: failed to connect` | MOUTH service unreachable from phone | Check port with `nc`; may be transient WiFi issue on first launch |
| No audio transcription | EARS WebSocket not connecting | Check logcat for WebSocket errors; verify `:30212` |
| No voice playback (text works) | MIND `tts_available: false` | Check MIND→MOUTH link: `curl http://192.168.50.2:30211/health` |
| `Ollama error: Request URL missing protocol` | `OLLAMA_HOST` env var missing `http://` prefix | Fix configmap `CICI_OLLAMA_HOST` to include full URL with protocol and port |
| `Ollama error: Name or service not known` | Wrong DNS name for Ollama in k8s | Fix configmap: use `http://local-llm.ai-ml.svc.cluster.local:11434` |
| App crashes on launch | Missing permission or SDK mismatch | Check `adb logcat` for `FATAL EXCEPTION` |
| Mic button doesn't work | `RECORD_AUDIO` permission not granted | `adb shell pm grant com.homelab.cici android.permission.RECORD_AUDIO` |
| Phone can't reach `192.168.50.2` | Phone not on same network / WiFi off | Check WiFi; try `adb reverse` port forwarding |

---

## Backend Troubleshooting (k8s)

When the Android app connects but features don't work, the issue is often in the k8s backend configuration.

### Verify MIND health (TTS status)

```bash
curl -s http://192.168.50.2:30211/health | python3 -m json.tool
```

Key field: `tts_available` — if `false`, MIND can't reach MOUTH. Check MIND pod env vars.

### Check MIND pod env vars

```bash
kubectl exec deployment/cici-mind -n ai-ml -- env | grep -E "MOUTH|OLLAMA"
```

Expected:
```
MOUTH_HOST=cici-mouth.ai-ml.svc.cluster.local
MOUTH_PORT=8001
OLLAMA_HOST=http://local-llm.ai-ml.svc.cluster.local:11434
OLLAMA_MODEL=hermes3
```

### Check MOUTH audio queue

```bash
curl -s http://192.168.50.2:30213/status
# {"pending_count":0,"completed_count":0} = idle
```

### Test DNS from inside MIND pod

```bash
kubectl exec deployment/cici-mind -n ai-ml -- python3 -c "
import socket
for name in ['cici-mouth', 'local-llm']:
    try:
        ip = socket.getaddrinfo(f'{name}.ai-ml.svc.cluster.local', None)
        print(f'{name}: {ip[0][4][0]}')
    except Exception as e:
        print(f'{name}: FAILED - {e}')
"
```

### Fix configmap and restart

```bash
# Patch configmap
kubectl patch configmap cici-config-dev -n ai-ml --type merge -p '{"data": {"KEY": "VALUE"}}'

# Restart pod to pick up changes
kubectl delete pod -n ai-ml -l app=cici-mind
```

### Known gotchas

- **`OLLAMA_HOST` must be a full URL** with `http://` and port — MIND concatenates paths onto it directly (e.g., `f"{ollama_host}/api/generate"`)
- **k8s service names have no `-dev` suffix** — the actual services are `cici-mind`, `cici-ears`, `cici-mouth`, `cici-face` (not `cici-mind-dev` etc.)
- **Ollama k8s service is named `local-llm`**, not `ollama` — the service is at `local-llm.ai-ml.svc.cluster.local:11434`
- **ConfigMap changes require pod restart** — k8s does not auto-restart pods when a referenced configmap changes; delete the pod to force it
- **ArgoCD GitOps**: k8s manifests live in `/infra/k8s-manifests/ai-ml/cici-*/`; push changes there and either wait for ArgoCD sync or `kubectl apply` directly

---

## Reading UI State Without a Screen

The dark theme makes screenshots nearly unreadable in remote sessions. Use `uiautomator dump` instead:

```bash
# Dump view hierarchy
adb shell uiautomator dump /sdcard/ui.xml

# Extract all visible text
adb shell cat /sdcard/ui.xml | grep -o 'text="[^"]*"'
```

This shows the status bar text (e.g., `MIND:OK  MOUTH:OK  [192.168.50.2]`), all chat messages, and error strings — far more useful than a screenshot.

---

## Quick Reference: Full Test Cycle

```bash
# 1. Build
cd /infra/ai-ml/cici/face-android && ./gradlew assembleDebug

# 2. Install
adb install -r app/build/outputs/apk/debug/app-debug.apk

# 3. Launch
adb shell am start -n com.homelab.cici/.MainActivity

# 4. Watch logs
adb logcat --pid=$(adb shell pidof com.homelab.cici)

# 5. Screenshot
adb exec-out screencap -p > /tmp/cici-screenshot.png

# 6. Iterate — edit Java source, rebuild, reinstall
```
