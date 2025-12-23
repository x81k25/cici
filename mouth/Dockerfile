FROM python:3.11-slim

WORKDIR /app

# Build args for Piper voice model
ARG PIPER_VOICE=en_GB-jenny_dioco-medium

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
COPY config/ ./config/

# Install dependencies with uv
RUN uv sync --no-dev

# Create models directory and download Piper voice model
# URL pattern: https://huggingface.co/rhasspy/piper-voices/resolve/main/{lang}/{lang_region}/{speaker}/{quality}/{voice}.onnx
RUN mkdir -p /models && \
    LANG_CODE=$(echo ${PIPER_VOICE} | cut -d'-' -f1 | cut -d'_' -f1) && \
    LANG_REGION=$(echo ${PIPER_VOICE} | cut -d'-' -f1) && \
    SPEAKER=$(echo ${PIPER_VOICE} | cut -d'-' -f2) && \
    QUALITY=$(echo ${PIPER_VOICE} | cut -d'-' -f3) && \
    BASE_URL="https://huggingface.co/rhasspy/piper-voices/resolve/main" && \
    curl -L -o /models/${PIPER_VOICE}.onnx \
        "${BASE_URL}/${LANG_CODE}/${LANG_REGION}/${SPEAKER}/${QUALITY}/${PIPER_VOICE}.onnx" && \
    curl -L -o /models/${PIPER_VOICE}.onnx.json \
        "${BASE_URL}/${LANG_CODE}/${LANG_REGION}/${SPEAKER}/${QUALITY}/${PIPER_VOICE}.onnx.json"

# Set environment variable for runtime
ENV PIPER_VOICE=${PIPER_VOICE}

EXPOSE 8001

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
