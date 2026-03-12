FROM python:3.11-slim

WORKDIR /app

# Install uv and system dependencies for piper-tts
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    curl \
    && curl -LsSf https://astral.sh/uv/install.sh | sh \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/root/.local/bin:$PATH"

# Copy root project files for dependency resolution
COPY pyproject.toml uv.lock README.md ./

# Copy mind module and config
COPY mind/mind/ ./mind/mind/
COPY mind/config/ ./config/

# Install dependencies with uv
RUN uv sync --no-dev --extra mind

# Create logs directory
RUN mkdir -p /app/logs

EXPOSE 8765

CMD ["uv", "run", "uvicorn", "mind.main:app", "--host", "0.0.0.0", "--port", "8765"]
