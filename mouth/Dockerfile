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

# Copy root project files for dependency resolution
COPY pyproject.toml uv.lock README.md ./

# Copy mouth module and config
COPY mouth/mouth/ ./mouth/mouth/
COPY mouth/config/ ./config/

# Install dependencies with uv
RUN uv sync --no-dev --extra mouth

# Create models directory and download Piper voice model
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

CMD ["uv", "run", "uvicorn", "mouth.main:app", "--host", "0.0.0.0", "--port", "8001"]
