# Stage 1: builder — install dependencies into a venv
FROM python:3.11-slim AS builder

ENV POETRY_VERSION=1.8.3 \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_HOME=/opt/poetry \
    PATH="/opt/poetry/bin:${PATH}"

WORKDIR /app/backend

RUN apt-get update && \
    apt-get install --no-install-recommends -y build-essential && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "poetry==${POETRY_VERSION}"

COPY backend/pyproject.toml backend/poetry.lock* ./
RUN poetry install --without dev --no-root --no-ansi

# Stage 2: runtime — copy only the venv and app code
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    NUMBA_CACHE_DIR=/tmp/numba_cache \
    PATH="/app/backend/.venv/bin:${PATH}"

WORKDIR /app

RUN apt-get update && \
    apt-get install --no-install-recommends -y ffmpeg libsndfile1 && \
    rm -rf /var/lib/apt/lists/*

RUN addgroup --system --gid 1000 app && adduser --system --uid 1000 --ingroup app app
RUN mkdir -p /tmp/numba_cache && chown app:app /tmp/numba_cache

# Copy virtualenv from builder
COPY --from=builder /app/backend/.venv /app/backend/.venv

# Copy application code and logging config
COPY --chown=app:app backend /app/backend
COPY --chown=app:app logging_config.json /app/logging_config.json

EXPOSE 8080

USER 1000:1000

CMD ["uvicorn", "backend.app.app:app", "--host", "0.0.0.0", "--port", "8080", "--log-config", "/app/logging_config.json"]
