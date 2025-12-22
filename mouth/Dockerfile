FROM python:3.11-slim

WORKDIR /app

# Install uv and Piper dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    curl \
    && curl -LsSf https://astral.sh/uv/install.sh | sh \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/root/.local/bin:$PATH"

# Copy project files
COPY pyproject.toml .
COPY app/ ./app/

# Install dependencies with uv
RUN uv sync --no-dev

# Create models directory (mount voice model at runtime)
RUN mkdir -p /models

EXPOSE 8001

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
