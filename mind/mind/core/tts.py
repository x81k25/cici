# standard library imports
import io
import subprocess
import wave
from pathlib import Path
from typing import Optional

# 3rd-party imports
from loguru import logger

# ------------------------------------------------------------------------------
# piper text-to-speech utility
# ------------------------------------------------------------------------------

# default voice model - will be downloaded on first use
DEFAULT_MODEL = "en_GB-cori-high"

# cache directory for models
MODELS_DIR = Path(__file__).parent.parent.parent / "models" / "piper"


def ensure_model(model_name: str = DEFAULT_MODEL) -> Path:
    """
    Ensure the piper model is downloaded.
    Returns path to model file.
    """
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    model_path = MODELS_DIR / f"{model_name}.onnx"
    config_path = MODELS_DIR / f"{model_name}.onnx.json"

    if model_path.exists() and config_path.exists():
        return model_path

    # download model using piper's built-in downloader
    logger.info(f"downloading piper model: {model_name}")
    try:
        subprocess.run(
            [
                "uv", "run", "python", "-m", "piper",
                "--model", model_name,
                "--download-dir", str(MODELS_DIR),
                "--update-voices",
            ],
            capture_output=True,
            text=True,
            timeout=120,
            input=""  # empty input to just trigger download
        )
        logger.info(f"model downloaded to {MODELS_DIR}")
    except Exception as e:
        logger.error(f"failed to download model: {e}")
        raise

    return model_path


def speak(
    text: str,
    model: str = DEFAULT_MODEL,
    output_file: Optional[str] = None,
    play: bool = True
) -> Optional[bytes]:
    """
    Convert text to speech using Piper.

    :param text: Text to speak
    :param model: Piper model name
    :param output_file: Optional path to save WAV file
    :param play: Whether to play audio immediately
    :return: WAV bytes if output_file is None and play is False
    """
    if not text or not text.strip():
        return None

    try:
        # get model path
        model_path = MODELS_DIR / f"{model}.onnx"
        if not model_path.exists():
            logger.error(f"model not found: {model_path}")
            return None

        # run piper via command line for simplicity
        cmd = [
            "uv", "run", "python", "-m", "piper",
            "--model", str(model_path),
            "--output-raw"
        ]

        logger.debug(f"speaking: {text[:50]}...")

        result = subprocess.run(
            cmd,
            input=text.encode('utf-8'),
            capture_output=True,
            timeout=30
        )

        if result.returncode != 0:
            logger.error(f"piper error: {result.stderr.decode()}")
            return None

        raw_audio = result.stdout

        if not raw_audio:
            logger.warning("piper produced no audio")
            return None

        # convert raw audio to WAV format
        # piper outputs raw 16-bit 22050Hz mono PCM
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(22050)
            wav_file.writeframes(raw_audio)

        wav_bytes = wav_buffer.getvalue()

        # save to file if requested
        if output_file:
            with open(output_file, 'wb') as f:
                f.write(wav_bytes)
            logger.info(f"saved audio to {output_file}")

        # play audio if requested
        if play:
            play_audio(wav_bytes)

        return wav_bytes

    except subprocess.TimeoutExpired:
        logger.error("piper timed out")
        return None
    except Exception as e:
        logger.error(f"tts error: {e}")
        return None


def play_audio(wav_bytes: bytes) -> None:
    """
    Play WAV audio bytes using available system player.
    """
    try:
        # try aplay (Linux ALSA)
        result = subprocess.run(
            ["aplay", "-q", "-"],
            input=wav_bytes,
            capture_output=True,
            timeout=30
        )
        if result.returncode == 0:
            return
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.debug(f"aplay failed: {e}")

    try:
        # try paplay (PulseAudio)
        result = subprocess.run(
            ["paplay", "--raw", "--rate=22050", "--channels=1", "--format=s16le"],
            input=wav_bytes[44:],  # skip WAV header for raw playback
            capture_output=True,
            timeout=30
        )
        if result.returncode == 0:
            return
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.debug(f"paplay failed: {e}")

    try:
        # try ffplay (FFmpeg)
        result = subprocess.run(
            ["ffplay", "-nodisp", "-autoexit", "-hide_banner", "-loglevel", "quiet", "-"],
            input=wav_bytes,
            capture_output=True,
            timeout=30
        )
        if result.returncode == 0:
            return
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.debug(f"ffplay failed: {e}")

    logger.warning("no audio player available (tried aplay, paplay, ffplay)")


# ------------------------------------------------------------------------------
# convenience functions
# ------------------------------------------------------------------------------

def say(text: str) -> None:
    """Simple wrapper to speak text immediately."""
    speak(text, play=True)


def say_command(command: str) -> None:
    """Announce a command confirmation."""
    speak(f"Confirming: {command}", play=True)


def say_complete() -> None:
    """Announce command completion."""
    speak("Complete", play=True)


def say_error(message: str) -> None:
    """Announce an error."""
    speak(f"Error: {message}", play=True)


# ------------------------------------------------------------------------------
# CLI for testing
# ------------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        text = " ".join(sys.argv[1:])
    else:
        text = "Hello, this is Cici text to speech."

    print(f"Speaking: {text}")
    say(text)
