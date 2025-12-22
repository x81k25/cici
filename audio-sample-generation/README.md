# Audio Sample Generation

Generates defective audio files for testing the EARS audio analyzer.

## Usage

```bash
cd audio-sample-generation
uv sync
uv run python generate_defective_audio.py <source.webm> --output-dir <output/> [--defects ...]
```

## Example

```bash
# Generate all defect types
uv run python generate_defective_audio.py ../tests/audio/recording.webm --output-dir ../tests/audio/defective

# Generate specific defects
uv run python generate_defective_audio.py source.webm --output-dir output --defects silence clipping wrong_sample_rate_slow
```

## Defect Types

| Defect | Output | Description |
|--------|--------|-------------|
| `low_volume` | `.webm` | Scales amplitude to 5% |
| `silence` | `.webm` | Zeros all samples |
| `clipping` | `.webm` | Applies 10x gain causing distortion |
| `dc_offset` | `.webm` | Adds +16000 DC bias |
| `wrong_sample_rate_slow` | `.webm` + `.raw` | Low-pass filtered (600Hz cutoff) - simulates slow playback |
| `wrong_sample_rate_fast` | `.webm` + `.raw` | High-pass filtered (4500Hz cutoff) - simulates fast playback |
| `wrong_chunk_small` | `.webm` | 50ms chunk instead of 100ms |
| `wrong_chunk_large` | `.webm` | 200ms chunk instead of 100ms |
| `wrong_byte_order` | `.webm` + `.raw` | Swapped endianness |
| `truncated` | `.webm` + `.raw` | Cut at 70% (mid-speech) |
| `noise_only` | `.webm` | Random samples replacing speech |

## Raw PCM Output

Some defects produce both `.webm` and `.raw` files because WebM encoding normalizes certain defects:

- **Sample rate defects**: WebM codec uses container metadata for sample rate
- **Byte order defects**: Opus codec handles endianness correctly
- **Truncated**: WebM codec may pad/handle truncation

The `.raw` files bypass codec normalization and are used for integration testing.

## Dependencies

- numpy
- scipy (for signal filtering)
- ffmpeg (must be installed on system)
