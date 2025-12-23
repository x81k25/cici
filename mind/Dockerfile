FROM python:3.11-slim

WORKDIR /app

# Install uv and system dependencies for piper-tts
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    curl \
    && curl -LsSf https://astral.sh/uv/install.sh | sh \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/root/.local/bin:$PATH"

# Copy project files
COPY pyproject.toml README.md ./
COPY mind/ ./mind/
COPY config/ ./config/

# Install dependencies with uv
RUN uv sync --no-dev

# Create logs directory
RUN mkdir -p /app/logs

EXPOSE 8765

CMD ["uv", "run", "uvicorn", "mind.main:app", "--host", "0.0.0.0", "--port", "8765"]
