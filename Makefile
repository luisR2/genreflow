
# Common Poetry targets
# Phony targets
.PHONY: install list check update run dev shell test lint venv help

# Command to run inside the Poetry environment (override when calling: make run CMD="python -m server")
CMD ?= python -m server

# Dev server command (override with: make dev CMD_DEV="uvicorn server:app --reload")
CMD_DEV ?= uvicorn server:app --reload

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
	poetry run ruff check . || poetry run flake8 .

venv:
	@if [ -n "$(PYTHON)" ]; then \
		echo "Setting poetry environment Python to $(PYTHON)"; \
		poetry env use $(PYTHON); \
	else \
		poetry env info --path || echo "No virtualenv found. Run 'make install' or 'make shell' to create one."; \
	fi

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
	@echo "  make help        -> show this help message"

