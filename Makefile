
# Common Poetry targets
# Phony targets
.PHONY: install install-hooks list check update run dev frontend shell test lint format black venv help docker-build-backend docker-build-frontend docker-build-all docker-run-backend docker-stop docker-login docker-push-backend docker-push-frontend docker-push-all

POETRY ?= poetry
POETRY_CMD := cd backend && $(POETRY)
POETRY_RUN := cd backend && $(POETRY) run

# Command to run inside the Poetry environment (override when calling: make run CMD="python -m backend")
CMD ?= uvicorn backend.app.app:app --port 8080 --log-config ../logging_config.json

# Dev server command (override with: make dev CMD_DEV="uvicorn backend.app.app:app --reload")
CMD_DEV ?= uvicorn backend.app.app:app --reload --port 8080 --log-config ../logging_config.json

# Frontend dev server command (override with: make frontend FRONTEND_CMD="uvicorn app:app --reload --port 3000")
FRONTEND_CMD ?= uvicorn app:app --reload --host 0.0.0.0 --port 3000 --log-config ../logging_config.json
 
# Backend API base URL consumed by the frontend (override per environment)
GENREFLOW_API_BASE_URL ?= http://localhost:8080

# Backend host used by the predict-file curl helper (can be overridden on the make command line)
HOST ?= http://127.0.0.1:8080
# Default top-k for predictions (can be overridden: make predict-file FILE=... TOP_K=5)
TOP_K ?= 3

# Docker image configuration
# IMPORTANT: Set DOCKERHUB_USERNAME to your Docker Hub username
# Usage: make docker-push DOCKERHUB_USERNAME=yourusername
DOCKERHUB_USERNAME ?= luisrr
BACKEND_IMAGE ?= $(DOCKERHUB_USERNAME)/genreflow-backend
FRONTEND_IMAGE ?= $(DOCKERHUB_USERNAME)/genreflow-frontend
BACKEND_CONTAINER ?= genreflow-backend
FRONTEND_CONTAINER ?= genreflow-frontend
IMAGE_TAG ?= $(shell git rev-parse --short HEAD 2>/dev/null || echo "latest")

# Pytest arguments (override with: make test PYTEST_ARGS="-q -k smoke")
PYTEST_ARGS ?= -raq

install:
	$(POETRY_CMD) install --with dev

install-hooks:
	$(POETRY_RUN) pre-commit install

list:
	$(POETRY_CMD) show --tree

check:
	$(POETRY_CMD) check

update:
	$(POETRY_CMD) update

run:
	$(POETRY_RUN) $(CMD)

dev:
	$(POETRY_RUN) $(CMD_DEV)

frontend:
	$(POETRY_RUN) sh -c 'cd ../frontend && GENREFLOW_API_BASE_URL="$(GENREFLOW_API_BASE_URL)" $(FRONTEND_CMD)'

test:
	$(POETRY_RUN) pytest $(PYTEST_ARGS)

lint:
	$(POETRY_RUN) ruff check .

format:
	$(POETRY_RUN) ruff format .

format-black:
	$(POETRY_RUN) black app/

venv:
	@$(POETRY_CMD) env info --path || (echo "No virtualenv found. Run 'make install' first." && exit 1)

shell:
	@echo "Activating Poetry shell... (use 'exit' to deactivate)"
	@$(POETRY_CMD) shell

# Upload a local audio file to the /predict/file endpoint.
# Usage: make predict-file FILE=/path/to/song.wav [HOST=http://127.0.0.1:8080]
predict-file:
	@if [ -z "$(FILE)" ]; then \
		echo "Usage: make predict-file FILE=/path/to/song.wav [HOST=http://127.0.0.1:8080]"; \
		exit 1; \
	fi
	@echo "Uploading $(FILE) to $(HOST)/predict/file ..."
	@curl -F "file=@$(FILE)" "$(HOST)/predict/file" || (echo "curl failed" && exit 2)

predict-files-bulk:
	@if [ -z "$(FILES)" ] && [ -z "$(FILES_LIST)" ]; then \
		echo "Usage: make predict-files-bulk FILES=\"/path/one.wav\\n/path/two.wav\" [HOST=$(HOST)]"; \
		echo "   or: make predict-files-bulk FILES_LIST=/path/to/list.txt [HOST=$(HOST)]"; \
		echo "FILES/FILES_LIST accept one path per line (preferred). Space-separated lists work if each path is quoted."; \
		exit 1; \
	fi
	@HOST="$(HOST)" FILES="$(FILES)" FILES_LIST="$(FILES_LIST)" python3 scripts/predict_files_bulk.py || (echo "curl failed" && exit 2)

help:
	@echo "Available targets:"
	@echo "  make install     -> create virtualenv and install dependencies via Poetry (with dev extras)"
	@echo "  make install-hooks -> install git pre-commit hooks (format + lint + tests)"
	@echo "  make check       -> run 'poetry check' to validate pyproject.toml and lockfile"
	@echo "  make update      -> update dependencies in pyproject.lock using Poetry"
	@echo "  make list        -> show dependency tree via 'poetry show --tree'"
	@echo "  make run CMD=..  -> run a command inside Poetry's virtualenv (default: $(CMD))"
	@echo "  make dev CMD_DEV=.. -> run development server inside Poetry (default: $(CMD_DEV))"
	@echo "  make frontend GENREFLOW_API_BASE_URL=.. -> run the frontend UI via uvicorn (default backend URL $(GENREFLOW_API_BASE_URL))"
	@echo "  make shell       -> open an interactive Poetry shell (activates venv)"
	@echo "  make test        -> run tests via pytest (poetry run pytest $(PYTEST_ARGS))"
	@echo "  make lint        -> run ruff to lint the repository (poetry run ruff check .)"
	@echo "  make format      -> run ruff formatter"
	@echo "  make black       -> run Black formatter"
	@echo "  make venv PYTHON=.. -> show poetry venv path or set the environment Python (poetry env use $(PYTHON))"
	@echo "  make docker-build-backend -> build the backend Docker image (BACKEND_IMAGE=$(BACKEND_IMAGE), IMAGE_TAG=$(IMAGE_TAG))"
	@echo "  make docker-build-frontend -> build the frontend Docker image (FRONTEND_IMAGE=$(FRONTEND_IMAGE), IMAGE_TAG=$(IMAGE_TAG))"
	@echo "  make docker-run-backend   -> build and run the backend Docker image (BACKEND_IMAGE=$(BACKEND_IMAGE), CONTAINER_NAME=$(BACKEND_CONTAINER))"
	@echo "  make docker-login -> log in to Docker Hub (interactive)"
	@echo "  make docker-push-backend DOCKERHUB_USERNAME=... [IMAGE_TAG=...] -> build and push backend to Docker Hub"
	@echo "  make docker-push-frontend DOCKERHUB_USERNAME=... [IMAGE_TAG=...] -> build and push frontend to Docker Hub"
	@echo "  make predict-file FILE=.. -> predict genre for an audio file (optional: TOP_K=3, HOST=$(HOST))"
	@echo "  make predict-files-bulk FILES=.. -> predict multiple audio files; supports FILES_LIST=path for long lists (optional: HOST=$(HOST))"
	@echo "  make help         -> show this help message"

docker-login:
	@echo "Logging in to Docker Hub..."
	@docker login

docker-build-backend:
	docker buildx build --platform linux/arm64 -t $(BACKEND_IMAGE):$(IMAGE_TAG) -f backend/Dockerfile .

docker-build-frontend:
	docker buildx build --platform linux/arm64 -t $(FRONTEND_IMAGE):$(IMAGE_TAG) -f frontend/Dockerfile .

docker-build-all: docker-build-backend docker-build-frontend

docker-run-backend: docker-build-backend
	docker run --rm -p 8080:8080 -d --name $(BACKEND_CONTAINER) $(BACKEND_IMAGE):$(IMAGE_TAG)

docker-run-frontend: docker-build-frontend
	docker run --rm -p 3000:3000 -d --name $(FRONTEND_CONTAINER) $(FRONTEND_IMAGE):$(IMAGE_TAG)

docker-stop:
	docker stop $(BACKEND_CONTAINER)

docker-push-backend: docker-build-backend
	@if [ -z "$(DOCKERHUB_USERNAME)" ] || [ "$(DOCKERHUB_USERNAME)" = "" ]; then \
		echo "ERROR: DOCKERHUB_USERNAME not set!"; \
		echo "Usage: make docker-push-backend DOCKERHUB_USERNAME=yourusername"; \
		exit 1; \
	fi
	@echo "Pushing $(BACKEND_IMAGE):$(IMAGE_TAG) to Docker Hub..."
	@docker push $(BACKEND_IMAGE):$(IMAGE_TAG)

docker-push-frontend: docker-build-frontend
	@if [ -z "$(DOCKERHUB_USERNAME)" ] || [ "$(DOCKERHUB_USERNAME)" = "" ]; then \
		echo "ERROR: DOCKERHUB_USERNAME not set!"; \
		echo "Usage: make docker-push-frontend DOCKERHUB_USERNAME=yourusername"; \
		exit 1; \
	fi
	@echo "Pushing $(FRONTEND_IMAGE):$(IMAGE_TAG) to Docker Hub..."
	@docker push $(FRONTEND_IMAGE):$(IMAGE_TAG)

docker-push-all: docker-push-backend docker-push-frontend

# Docker compose commands
compose-up:
	docker compose up -d

compose-down:
	docker compose down


#TODO: Add a target to kubeseal the docker hub secret before pushing the YAML to GitHub.
