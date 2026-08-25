FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# Keep Python output unbuffered and avoid pyc writes at runtime.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Install dependencies first for better Docker layer caching.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Copy only application code required at runtime.
COPY README.md ./
COPY app ./app

# Install the project into the environment after source is present.
RUN uv sync --frozen --no-dev

# Create and use a non-root user. The app's .venv must be writable by that user.
RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
