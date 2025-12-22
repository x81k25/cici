#!/usr/bin/env python3
"""
Generate defective audio files for testing audio processing pipelines.

This script takes a source WebM audio file and produces variations with
specific defects for testing error handling and edge cases.

Defect types:
- low_volume: Scale samples by 0.01-0.1
- silence: Zero out the array
- clipping: Multiply samples until they hit ±32767
- dc_offset: Add constant value to all samples
- wrong_sample_rate: Resample interpretation mismatch
- wrong_chunk_size_small: 50ms chunks instead of 100ms
- wrong_chunk_size_large: 200ms chunks instead of 100ms
- wrong_byte_order: Swap endianness
- truncated: Chop mid-chunk
- noise_only: Replace with random samples
"""

import argparse
import subprocess
import sys
from pathlib import Path

import numpy as np


def decode_webm_to_pcm(input_path: Path, sample_rate: int = 16000) -> np.ndarray:
    """Decode WebM to raw PCM int16 samples."""
    cmd = [
        "ffmpeg",
        "-i", str(input_path),
        "-f", "s16le",
        "-acodec", "pcm_s16le",
        "-ar", str(sample_rate),
        "-ac", "1",
        "-",
    ]
    result = subprocess.run(cmd, capture_output=True, check=True)
    return np.frombuffer(result.stdout, dtype=np.int16)


def encode_pcm_to_webm(
    samples: np.ndarray,
    output_path: Path,
    sample_rate: int = 16000,
    sample_format: str = "s16le",
) -> None:
    """Encode raw PCM samples to WebM/Opus."""
    cmd = [
        "ffmpeg",
        "-y",
        "-f", sample_format,
        "-ar", str(sample_rate),
        "-ac", "1",
        "-i", "-",
        "-c:a", "libopus",
        "-b:a", "32k",
        str(output_path),
    ]
    subprocess.run(cmd, input=samples.tobytes(), capture_output=True, check=True)


def save_raw_pcm(samples: np.ndarray, output_path: Path) -> None:
    """Save raw PCM samples to file (for byte-order testing)."""
    samples.tofile(output_path)


def generate_low_volume(samples: np.ndarray, scale: float = 0.05) -> np.ndarray:
    """Scale samples to very low volume (0.01-0.1 range)."""
    return (samples.astype(np.float32) * scale).astype(np.int16)


def generate_silence(samples: np.ndarray) -> np.ndarray:
    """Zero out all samples."""
    return np.zeros_like(samples)


def generate_clipping(samples: np.ndarray, gain: float = 10.0) -> np.ndarray:
    """Apply heavy gain causing clipping at ±32767."""
    amplified = samples.astype(np.float32) * gain
    return np.clip(amplified, -32767, 32767).astype(np.int16)


def generate_dc_offset(samples: np.ndarray, offset: int = 16000) -> np.ndarray:
    """Add constant DC offset to all samples."""
    with_offset = samples.astype(np.float32) + offset
    return np.clip(with_offset, -32768, 32767).astype(np.int16)


def generate_wrong_sample_rate_48k_as_16k(samples: np.ndarray) -> np.ndarray:
    """
    Simulate audio recorded at 48kHz being interpreted as 16kHz.

    Creates audio with abnormally low spectral content (centroid < 800 Hz)
    by low-pass filtering to remove all frequencies above 600 Hz.
    This simulates what happens when audio plays 3x slower than intended.
    """
    from scipy import signal

    # Low-pass filter: remove everything above 600 Hz
    # This creates audio with clearly low spectral content
    nyquist = 16000 / 2
    cutoff = 600 / nyquist
    b, a = signal.butter(4, cutoff, btype='low')
    filtered = signal.filtfilt(b, a, samples.astype(np.float64))
    return np.clip(filtered, -32767, 32767).astype(np.int16)


def generate_wrong_sample_rate_16k_as_48k(samples: np.ndarray) -> np.ndarray:
    """
    Simulate audio recorded at 16kHz being interpreted as 48kHz.

    Creates audio with abnormally high spectral content (centroid > 4000 Hz)
    by high-pass filtering to remove all frequencies below 4500 Hz.
    This simulates what happens when audio plays 3x faster than intended.
    """
    from scipy import signal

    # High-pass filter: remove everything below 4500 Hz
    # This creates audio with clearly high spectral content
    nyquist = 16000 / 2
    cutoff = 4500 / nyquist
    b, a = signal.butter(4, cutoff, btype='high')
    filtered = signal.filtfilt(b, a, samples.astype(np.float64))
    return np.clip(filtered, -32767, 32767).astype(np.int16)


def generate_wrong_chunk_size_small(
    samples: np.ndarray, sample_rate: int = 16000
) -> np.ndarray:
    """
    Return samples sized for 50ms chunks instead of expected 100ms.
    Just truncate to 50ms worth of samples.
    """
    chunk_50ms = int(sample_rate * 0.05)  # 800 samples at 16kHz
    return samples[:chunk_50ms].copy()


def generate_wrong_chunk_size_large(
    samples: np.ndarray, sample_rate: int = 16000
) -> np.ndarray:
    """
    Return samples sized for 200ms chunks instead of expected 100ms.
    Repeat audio to fill 200ms.
    """
    chunk_200ms = int(sample_rate * 0.2)  # 3200 samples at 16kHz
    if len(samples) >= chunk_200ms:
        return samples[:chunk_200ms].copy()
    # Tile to reach 200ms
    repeats = (chunk_200ms // len(samples)) + 1
    return np.tile(samples, repeats)[:chunk_200ms]


def generate_wrong_byte_order(samples: np.ndarray) -> np.ndarray:
    """Swap endianness of samples."""
    return samples.byteswap()


def generate_truncated(samples: np.ndarray, fraction: float = 0.70) -> np.ndarray:
    """
    Truncate audio mid-speech to trigger truncation detection.

    The truncation point is set at 70% to ensure we cut during speech
    (assuming speech starts ~30% into the audio after initial silence).
    The last chunk must have RMS > 0.05 for detection.
    """
    cut_point = int(len(samples) * fraction)
    # Make it an odd number to simulate improper truncation
    if cut_point % 2 == 0:
        cut_point += 1
    return samples[:cut_point].copy()


def generate_noise_only(samples: np.ndarray) -> np.ndarray:
    """Replace all audio with random noise."""
    return np.random.randint(-32768, 32767, size=len(samples), dtype=np.int16)


def main():
    parser = argparse.ArgumentParser(
        description="Generate defective audio files for testing"
    )
    parser.add_argument(
        "source",
        type=Path,
        help="Source WebM audio file to use as base",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output"),
        help="Output directory for generated files",
    )
    parser.add_argument(
        "--sample-rate",
        type=int,
        default=16000,
        help="Target sample rate for processing (default: 16000)",
    )
    parser.add_argument(
        "--defects",
        nargs="+",
        choices=[
            "all",
            "low_volume",
            "silence",
            "clipping",
            "dc_offset",
            "wrong_sample_rate_slow",
            "wrong_sample_rate_fast",
            "wrong_chunk_small",
            "wrong_chunk_large",
            "wrong_byte_order",
            "truncated",
            "noise_only",
        ],
        default=["all"],
        help="Which defects to generate",
    )
    args = parser.parse_args()

    if not args.source.exists():
        print(f"Error: Source file not found: {args.source}", file=sys.stderr)
        sys.exit(1)

    args.output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading source audio: {args.source}")
    samples = decode_webm_to_pcm(args.source, args.sample_rate)
    print(f"  Loaded {len(samples)} samples ({len(samples)/args.sample_rate:.2f}s)")

    defects_to_generate = args.defects
    if "all" in defects_to_generate:
        defects_to_generate = [
            "low_volume",
            "silence",
            "clipping",
            "dc_offset",
            "wrong_sample_rate_slow",
            "wrong_sample_rate_fast",
            "wrong_chunk_small",
            "wrong_chunk_large",
            "wrong_byte_order",
            "truncated",
            "noise_only",
        ]

    generators = {
        "low_volume": (
            generate_low_volume,
            {"scale": 0.05},
            "Low volume (5% amplitude)",
        ),
        "silence": (
            generate_silence,
            {},
            "Complete silence",
        ),
        "clipping": (
            generate_clipping,
            {"gain": 10.0},
            "Heavy clipping (10x gain)",
        ),
        "dc_offset": (
            generate_dc_offset,
            {"offset": 16000},
            "DC offset (+16000)",
        ),
        "wrong_sample_rate_slow": (
            generate_wrong_sample_rate_48k_as_16k,
            {},
            "48kHz interpreted as 16kHz (plays slow)",
        ),
        "wrong_sample_rate_fast": (
            generate_wrong_sample_rate_16k_as_48k,
            {},
            "16kHz interpreted as 48kHz (plays fast)",
        ),
        "wrong_chunk_small": (
            lambda s: generate_wrong_chunk_size_small(s, args.sample_rate),
            {},
            "50ms chunk (instead of 100ms)",
        ),
        "wrong_chunk_large": (
            lambda s: generate_wrong_chunk_size_large(s, args.sample_rate),
            {},
            "200ms chunk (instead of 100ms)",
        ),
        "wrong_byte_order": (
            generate_wrong_byte_order,
            {},
            "Swapped endianness",
        ),
        "truncated": (
            generate_truncated,
            {"fraction": 0.70},
            "Truncated at 70% (mid-speech)",
        ),
        "noise_only": (
            generate_noise_only,
            {},
            "Random noise only",
        ),
    }

    for defect_name in defects_to_generate:
        if defect_name not in generators:
            print(f"Warning: Unknown defect type: {defect_name}", file=sys.stderr)
            continue

        gen_func, kwargs, description = generators[defect_name]
        print(f"\nGenerating: {defect_name}")
        print(f"  Description: {description}")

        try:
            if kwargs:
                defective_samples = gen_func(samples, **kwargs)
            else:
                defective_samples = gen_func(samples)

            output_path = args.output_dir / f"defect_{defect_name}.webm"
            encode_pcm_to_webm(defective_samples, output_path, args.sample_rate)
            print(f"  Output: {output_path}")
            print(f"  Samples: {len(defective_samples)}")

            # For defects that get normalized by WebM codec, also save raw PCM
            if defect_name in ("wrong_byte_order", "wrong_sample_rate_slow", "wrong_sample_rate_fast", "truncated"):
                raw_path = args.output_dir / f"defect_{defect_name}.raw"
                save_raw_pcm(defective_samples, raw_path)
                print(f"  Raw PCM: {raw_path}")

        except Exception as e:
            print(f"  Error: {e}", file=sys.stderr)

    print("\nDone!")


if __name__ == "__main__":
    main()
