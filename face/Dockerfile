FROM python:3.11-slim

WORKDIR /app

# Install uv and system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && curl -LsSf https://astral.sh/uv/install.sh | sh \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/root/.local/bin:$PATH"

# Copy project files
COPY pyproject.toml .
COPY app.py .
COPY config.py .
COPY mind_client.py .
COPY mouth_client.py .
COPY config/ ./config/
COPY pages/ ./pages/
COPY utils/ ./utils/
COPY static/ ./static/
COPY .streamlit/ ./.streamlit/

# Override Streamlit config for Docker (no SSL)
RUN echo '[server]\nenableStaticServing = true\n' > .streamlit/config.toml

# Install dependencies with uv
RUN uv sync --no-dev

# Install playwright browsers (optional - for testing features only)
# RUN uv run playwright install chromium --with-deps

EXPOSE 8501

# Streamlit configuration via environment
ENV STREAMLIT_SERVER_PORT=8501
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0
ENV STREAMLIT_SERVER_HEADLESS=true

CMD ["uv", "run", "streamlit", "run", "app.py"]
