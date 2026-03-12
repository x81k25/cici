FROM 192.168.50.2:5050/ai-ml/torch-base:torch2.5-cu121

WORKDIR /app

# Copy root project files for dependency resolution
COPY pyproject.toml uv.lock ./

# Copy ears module
COPY ears/ears/ ./ears/ears/

# Install app-specific dependencies (torch, faster-whisper already in base)
RUN uv pip install --system --no-cache-dir ".[ears]"

# Create cache directory for Whisper models
RUN mkdir -p /root/.cache/huggingface

EXPOSE 8766

CMD ["python", "-m", "ears.main"]
