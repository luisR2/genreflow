# GenreFlow Roadmap

## Phase 1: MVP (Current)
- [x] Basic genre classification
- [x] FastAPI backend
- [x] Docker containerization
- [x] Create k8s backend deployment
- [x] Test argoCD on PIs
- [x] Deploy backend using argocD
- [x] Draft a Web interface
- [x] Create k8s frontend deployment
- [x] Deploy frontend using argoCD

## Phase 2: Production Ready

- [ ] Test security concerns
- [ ] Reduce processing time to <10s per track


## Phase 3: Enhanced Features
- [ ] Batch processing for playlists
- [ ] Key detection
- [ ] Observability stack (Prometheus/Grafana)



## Backend Code Quality Sprint

> All changes committed directly to `main` (trunk-based development).

### Part 1 — Critical Bug Fixes & Security ✅
- [x] `filename` None guard in file validation (`routes_file.py`)
- [x] Validate file content with `filetype` (magic bytes), not extension only (`routes_file.py`) — replaced `python-magic` with pure-Python `filetype`
- [x] Global exception handler: return generic message, log detail server-side (`app.py`)
- [x] Move `librosa` import out of hot loop in `estimate_bpm` (`predict.py`)

### Part 2 — Architecture Refactoring ✅
- [x] Replace deprecated `on_event` with `lifespan` context manager (`app.py`)
- [x] Move `Predictor` init into `lifespan` via `app.state` (fixes logging-before-config bug)
- [x] Move `HealthResponse`/`ReadinessResponse` to `schemas.py`
- [x] Remove dead `Predictor` methods (`_heuristic_window_prediction`, `_windows`, `_get_song_bpm`)
- [x] Remove unused `prometheus-client` dependency

### Part 3 — Performance & Resilience ✅
- [x] Parallelise `/predict/files` with `asyncio.gather`
- [x] Enforce file size limit (reject >50 MB with 413)
- [x] Enforce batch size limit on `/predict/files` (reject >20 files with 413)

### Part 4 — Test Coverage ✅
- [x] Negative-path tests for all new validations (extension, magic bytes, size, batch limit)
- [x] Edge case tests (corrupt file, empty file, silent audio)
- [x] Convert module-level `TestClient` to `pytest` fixtures

### Part 5 — Housekeeping ✅
- [x] Pin major version constraints on all production deps
- [x] Move `requests` to dev group
- [x] Remove `black` (redundant with `ruff format`)
- [x] Multi-stage Dockerfile
- [x] Default `IMAGE_TAG` to git SHA

## Future Work
- Spotify playlist prediction and integration
- Replace heuristic-based music analysis with ML models (genre, BPM, key detection)
