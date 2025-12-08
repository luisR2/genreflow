FROM python:3.11-slim

WORKDIR /app

COPY frontend/ /app/
COPY logging_config.json /app/logging_config.json

RUN pip install --no-cache-dir fastapi "uvicorn[standard]"

ENV GENREFLOW_API_BASE_URL="http://genreflow-backend:8080"

EXPOSE 3000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "3000", "--log-config", "/app/logging_config.json"]
