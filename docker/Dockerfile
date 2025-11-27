FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    POETRY_VERSION=1.8.3 \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_HOME=/opt/poetry \
    PATH="/opt/poetry/bin:${PATH}"

WORKDIR /app

# System dependencies required by numpy, scipy, librosa, and soundfile
RUN apt-get update && \
    apt-get install --no-install-recommends -y \
        build-essential \
        ffmpeg \
        libsndfile1 \
        libmagic1 \
        file && \
    rm -rf /var/lib/apt/lists/*

RUN addgroup --system app && adduser --system --ingroup app app

# Install Poetry and project dependencies
RUN pip install --no-cache-dir "poetry==${POETRY_VERSION}"

COPY pyproject.toml poetry.lock* /app/
RUN poetry install --without dev --no-root --no-ansi
# Remove build tools to slim the image
RUN apt-get purge -y build-essential && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

# Copy application code
COPY --chown=app:app . /app

EXPOSE 8080

USER app

CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "8080"]
