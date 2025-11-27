
# Common Poetry targets
# Phony targets
.PHONY: install list check update run dev shell test lint venv help docker-build docker-run docker-push docker-login

# Command to run inside the Poetry environment (override when calling: make run CMD="python -m server")
CMD ?= uvicorn server.app:app --port 8080

# Dev server command (override with: make dev CMD_DEV="uvicorn server:app --reload")
CMD_DEV ?= uvicorn server.app:app --reload --port 8080
 
# Server host used by the predict-file curl helper (can be overridden on the make command line)
HOST ?= http://127.0.0.1:8080
# Default top-k for predictions (can be overridden: make predict-file FILE=... TOP_K=5)
TOP_K ?= 3

# Docker image configuration
# IMPORTANT: Set DOCKERHUB_USERNAME to your Docker Hub username
# Usage: make docker-push DOCKERHUB_USERNAME=yourusername
DOCKERHUB_USERNAME ?= luisrr
IMAGE_NAME ?= $(DOCKERHUB_USERNAME)/genreflow-server
CONTAINER_NAME ?= genreflow-api
IMAGE_TAG ?= latest

# Pytest arguments (override with: make test PYTEST_ARGS="-q -k smoke")
PYTEST_ARGS ?= -q

install:
	poetry install --with dev

list:
	poetry show --tree

check:
	poetry check

update:
	poetry update

run:
	poetry run $(CMD)

dev:
	poetry run $(CMD_DEV)

test:
	poetry run pytest $(PYTEST_ARGS)

lint:
	poetry run ruff check .

format:
	poetry run ruff format .

venv:
	@poetry env info --path || (echo "No virtualenv found. Run 'make install' first." && exit 1)

shell:
	@echo "Activating Poetry shell... (use 'exit' to deactivate)"
	@poetry shell

# Upload a local audio file to the /predict/file endpoint.
# Usage: make predict-file FILE=/path/to/song.wav [TOP_K=3] [HOST=http://127.0.0.1:8080]
predict-file:
	@if [ -z "$(FILE)" ]; then \
		echo "Usage: make predict-file FILE=/path/to/song.wav [TOP_K=3] [HOST=http://127.0.0.1:8080]"; \
		exit 1; \
	fi
	@echo "Uploading $(FILE) to $(HOST)/predict/file?top_k=$(TOP_K) ..."
	@curl -F "file=@$(FILE)" "$(HOST)/predict/file?top_k=$(TOP_K)" || (echo "curl failed" && exit 2)

help:
	@echo "Available targets:"
	@echo "  make install    -> create virtualenv and install dependencies via Poetry (with dev extras)"
	@echo "  make check      -> run 'poetry check' to validate pyproject.toml and lockfile"
	@echo "  make update     -> update dependencies in pyproject.lock using Poetry"
	@echo "  make list        -> show dependency tree via 'poetry show --tree'"
	@echo "  make run CMD=.. -> run a command inside Poetry's virtualenv (default: $(CMD))"
	@echo "  make dev CMD_DEV=.. -> run development server inside Poetry (default: $(CMD_DEV))"
	@echo "  make shell       -> open an interactive Poetry shell (activates venv)"
	@echo "  make test        -> run tests via pytest (poetry run pytest $(PYTEST_ARGS))"
	@echo "  make lint        -> run ruff to lint the repository (poetry run ruff check .)"
	@echo "  make venv PYTHON=.. -> show poetry venv path or set the environment Python (poetry env use $(PYTHON))"
	@echo "  make docker-build -> build the Docker image (IMAGE_NAME=$(IMAGE_NAME), IMAGE_TAG=$(IMAGE_TAG))"
	@echo "  make docker-run   -> build and run the Docker image (IMAGE_NAME=$(IMAGE_NAME), CONTAINER_NAME=$(CONTAINER_NAME))"
	@echo "  make docker-login -> log in to Docker Hub (interactive)"
	@echo "  make docker-push DOCKERHUB_USERNAME=... [IMAGE_TAG=...] -> build and push to Docker Hub"
	@echo "  make predict-file FILE=.. -> predict genre for an audio file (optional: TOP_K=3, HOST=$(HOST))"
	@echo "  make help         -> show this help message"

docker-build:
	docker buildx build --platform linux/arm64 -t $(IMAGE_NAME) -f docker/Dockerfile .

docker-run: docker-build
	docker run --rm -p 8080:8080 -d --name $(CONTAINER_NAME) $(IMAGE_NAME):$(IMAGE_TAG)

docker-stop:
	docker stop $(CONTAINER_NAME)

docker-login:
	@echo "Logging in to Docker Hub..."
	@docker login

docker-push: docker-build
	@if [ -z "$(DOCKERHUB_USERNAME)" ] || [ "$(DOCKERHUB_USERNAME)" = "" ]; then \
		echo "ERROR: DOCKERHUB_USERNAME not set!"; \
		echo "Usage: make docker-push DOCKERHUB_USERNAME=yourusername"; \
		exit 1; \
	fi
	@echo "Pushing $(IMAGE_NAME):$(IMAGE_TAG) to Docker Hub..."
	@docker push $(IMAGE_NAME):$(IMAGE_TAG)

