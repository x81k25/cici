FROM python:3.11-slim

WORKDIR /app

# Install uv, FFmpeg (for pydub), and audio processing dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    && curl -LsSf https://astral.sh/uv/install.sh | sh \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/root/.local/bin:$PATH"

# Copy project files
COPY pyproject.toml README.md ./
COPY ears/ ./ears/

# Install dependencies with uv (uses CPU torch by default)
RUN uv sync --no-dev

# Create cache directory for Whisper models
RUN mkdir -p /root/.cache/huggingface

EXPOSE 8766

CMD ["uv", "run", "python", "-m", "ears.main"]
