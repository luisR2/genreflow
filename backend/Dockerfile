FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    POETRY_VERSION=1.8.3 \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_HOME=/opt/poetry \
    NUMBA_CACHE_DIR=/tmp/numba_cache \
    PATH="/opt/poetry/bin:${PATH}"

WORKDIR /app

# System dependencies required by numpy, scipy, librosa, and soundfile
RUN apt-get update && \
    apt-get install --no-install-recommends -y \
        build-essential \
        ffmpeg \
        libsndfile1 && \
    rm -rf /var/lib/apt/lists/*

RUN addgroup --system --gid 1000 app && adduser --system --uid 1000 --ingroup app app
RUN mkdir -p /tmp/numba_cache && chown app:app /tmp/numba_cache

# Install Poetry and project dependencies
RUN pip install --no-cache-dir "poetry==${POETRY_VERSION}"

WORKDIR /app/backend
COPY backend/pyproject.toml backend/poetry.lock* ./
RUN poetry install --without dev --no-root --no-ansi

# Remove build tools to slim the image
RUN apt-get purge -y build-essential && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

# Copy application code and shared logging config
WORKDIR /app
COPY --chown=app:app backend /app/backend
COPY --chown=app:app logging_config.json /app/logging_config.json

EXPOSE 8080

USER 1000:1000

CMD ["uvicorn", "backend.app.app:app", "--host", "0.0.0.0", "--port", "8080", "--log-config", "/app/logging_config.json"]
