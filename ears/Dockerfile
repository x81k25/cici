FROM 192.168.50.2:5050/ai-ml/torch-base:torch2.5-cu121

WORKDIR /app

# Copy project files
COPY pyproject.toml README.md ./
COPY ears/ ./ears/

# Install app-specific dependencies only (torch, faster-whisper already in base)
RUN uv pip install --system --no-cache-dir \
    aiohttp \
    httpx \
    loguru \
    prometheus-client \
    pydantic \
    pydantic-settings \
    pydub \
    python-dotenv \
    pyyaml \
    silero-vad \
    websockets

# Create cache directory for Whisper models
RUN mkdir -p /root/.cache/huggingface

EXPOSE 8766

CMD ["python", "-m", "ears.main"]
