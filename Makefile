
# Common Poetry targets
# Phony targets
.PHONY: install list check update run dev shell test lint venv help

# Command to run inside the Poetry environment (override when calling: make run CMD="python -m server")
CMD ?= uvicorn server.app:app --port 8080

# Dev server command (override with: make dev CMD_DEV="uvicorn server:app --reload")
CMD_DEV ?= uvicorn server.app:app --reload --port 8080
 
# Server host used by the predict-file curl helper (can be overridden on the make command line)
HOST ?= http://127.0.0.1:8080
# Default top-k for predictions (can be overridden: make predict-file FILE=... TOP_K=5)
TOP_K ?= 3

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
	@echo "  make predict-file FILE=.. -> predict genre for an audio file (optional: TOP_K=3, HOST=$(HOST))"
	@echo "  make help        -> show this help message"

