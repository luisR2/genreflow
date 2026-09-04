# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

GenreFlow is a music genre classifier that analyzes audio files for BPM (tempo). It consists of a FastAPI backend for audio processing and a minimal HTML/CSS/JS frontend. The project deploys to a k3s Raspberry Pi cluster using ArgoCD for GitOps.

**Current Status**: MVP phase - only BPM analysis is implemented. Genre classification uses a heuristic placeholder that will be replaced with ML models (ONNX/TFLite).

## Common Commands

All commands run from the repository root via Make:

```bash
# Setup
make install              # Install dependencies via Poetry

# Development
make dev                  # Run backend with hot-reload on port 8080
make frontend             # Run frontend on port 3000 (set GENREFLOW_API_BASE_URL if needed)

# Testing & Linting
make test                 # Run pytest
make test PYTEST_ARGS="-k test_name"  # Run specific test
make lint                 # Run ruff linter
make format               # Format code with ruff

# Docker
make compose-up           # Start both services locally
make compose-down         # Stop services
make docker-build-all     # Build backend and frontend images (arm64)
```

## Architecture

```
User -> Frontend (port 3000) -> /api proxy -> Backend (port 8080) -> Audio Processing (librosa)
                 ^ only origin the browser sees      ^ ClusterIP only, no ingress
```

**Backend** (`backend/`):
- `app/app.py` - FastAPI entrypoint, lifespan, health checks, exception handler
- `app/predict.py` - `Predictor` class: loads audio, resamples to 16kHz, estimates BPM using librosa
- `app/routes_file.py` - File upload endpoints (`POST /predict/file`, `POST /predict/files`)
- `app/schemas.py` - Pydantic models (`BPMResult`, `BPMBulkResponse`)

**Frontend** (`frontend/`):
- Minimal FastAPI serving static HTML/CSS/JS
- Drag-and-drop file upload UI, uploading one file per request
- Proxies uploads to the backend at `POST /api/predict/{file,files}`, so the
  browser only ever talks to the frontend's own origin. The backend is
  ClusterIP-only with no ingress, and needs no CORS.

**API Endpoints** (backend, reachable only via the frontend proxy):
- `GET /healthz` - Liveness probe
- `GET /readyz` - Readiness probe (checks if predictor loaded)
- `POST /predict/file` - Single file BPM analysis
- `POST /predict/files` - Bulk BPM analysis, max 8 files (scripted callers only;
  the UI uploads one file per request)

**Frontend endpoints** (what the browser actually calls):
- `GET /` - SPA shell, `GET /healthz` - liveness
- `POST /api/predict/file` - proxied to the backend. The UI sends one request per
  file and renders each result as it lands, so no single request has to carry a
  whole selection.
- `POST /api/predict/files` - also proxied, but unused by the browser.

## Code Style

- Python 3.11+, strict typing enforced via MyPy
- Ruff for linting (line length 110, Google-style docstrings)
- All functions require type annotations (except tests)
- Tests live in `backend/tests/`

## Environment Variables

- `GENREFLOW_API_BASE_URL` - Backend URL the frontend proxies to (default: `http://localhost:8080`).
  Internal only; never a public address.
- `GENREFLOW_UPSTREAM_TIMEOUT` - Frontend proxy timeout in seconds (default: `120`)

## Branching Strategy

This project uses **trunk-based development**. All changes go directly to `main`.

- Short-lived feature branches are acceptable for large changes, but merge to `main` quickly.
- There is no long-lived `dev` branch — `main` is always the source of truth.

## Deployment

- Kubernetes manifests in `k8s/` (Kustomize base/overlay structure)
- ArgoCD applications in `k8s/argocd/`
- Docker images built for linux/arm64 (Raspberry Pi)
- Sealed secrets for Docker Hub credentials
