FROM python:3.11-slim

WORKDIR /app

# Install uv and system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && curl -LsSf https://astral.sh/uv/install.sh \
    | sh \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/root/.local/bin:$PATH"

# Copy root project files for dependency resolution
COPY pyproject.toml uv.lock README.md ./

# Copy face application files
COPY face/app.py .
COPY face/config.py .
COPY face/metrics.py .
COPY face/mind_client.py .
COPY face/mouth_client.py .
COPY face/config/ ./config/
COPY face/pages/ ./pages/
COPY face/utils/ ./utils/
COPY face/static/ ./static/
COPY face/.streamlit/ ./.streamlit/

# Override Streamlit config for Docker (no SSL)
RUN echo '[server]\nenableStaticServing = true\n' > .streamlit/config.toml

# Install dependencies with uv
RUN uv sync --no-dev --extra face

# Install playwright browsers (optional - for testing features only)
# RUN uv run playwright install chromium --with-deps

EXPOSE 8501

# Streamlit configuration via environment
ENV STREAMLIT_SERVER_PORT=8501
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0
ENV STREAMLIT_SERVER_HEADLESS=true

CMD ["uv", "run", "streamlit", "run", "app.py"]
