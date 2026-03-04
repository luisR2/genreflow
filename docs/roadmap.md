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
- [ ]   

## Phase 2: Production Ready

- [ ] Test security concerns
- [ ] Reduce processing time to <10s per track
  

## Phase 3: Enhanced Features
- [ ] Batch processing for playlists
- [ ] Key detection
- [ ] Observability stack (Prometheus/Grafana)



## Backend Code Quality Sprint

> Branches merge sequentially into `dev`. Parts 1→2→3→4, Part 5 is independent.

### Part 1 — Critical Bug Fixes & Security (`fix/critical-bugs-security`) ✅
- [x] `filename` None guard in file validation (`routes_file.py`)
- [x] Validate file content with `filetype` (magic bytes), not extension only (`routes_file.py`) — replaced `python-magic` with pure-Python `filetype`
- [x] Global exception handler: return generic message, log detail server-side (`app.py`)
- [x] Move `librosa` import out of hot loop in `estimate_bpm` (`predict.py`)

### Part 2 — Architecture Refactoring (`refactor/app-architecture`)
- [ ] Replace deprecated `on_event` with `lifespan` context manager (`app.py`)
- [ ] Move `Predictor` init into `lifespan` (fixes logging-before-config bug)
- [ ] Move `HealthResponse`/`ReadinessResponse` to `schemas.py`
- [ ] Remove dead `Predictor` methods (`_heuristic_window_prediction`, `_windows`, `_get_song_bpm`)
- [ ] Remove unused `prometheus-client` dependency

### Part 3 — Performance & Resilience (`feat/performance-resilience`)
- [ ] Parallelise `/predict/files` with `asyncio.gather`
- [ ] Enforce file size limit (reject >N MB with 413)
- [ ] Enforce batch size limit on `/predict/files`

### Part 4 — Test Coverage (`test/expand-coverage`)
- [ ] Negative-path tests for all new validations (extension, magic bytes, size, batch limit)
- [ ] Edge case tests (corrupt file, empty file, silent audio)
- [ ] Convert module-level `TestClient` to `pytest` fixtures

### Part 5 — Housekeeping (`chore/housekeeping`) — independent
- [ ] Pin major version constraints on all production deps
- [ ] Move `requests` to dev/scripts group
- [ ] Remove `black` (redundant with `ruff format`)
- [ ] Multi-stage Dockerfile
- [ ] Default `IMAGE_TAG` to git SHA

## Future Work
- Spotify playlist prediction and integration
- Replace heuristic-based music analysis with ML models (genre, BPM, key detection)