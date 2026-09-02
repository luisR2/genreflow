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

> Go-live sequencing lives in [go-live-plan.md](./go-live-plan.md).
> Exposure method: Cloudflare Tunnel.

- [ ] Test security concerns
- [x] Reduce processing time to <10s per track

### Tempo analysis performance

Analysis of a 4.5 minute track went from ~9.0s to ~0.6s on the dev machine
(~14x), and runtime is now flat with track length instead of linear.

- Cap analysis to a centred 60s excerpt (`DEFAULT_MAX_ANALYSIS_SECONDS`).
  Tempo is near-stationary, so a representative slice gives the same answer;
  verified identical BPM for 60s / 120s / 300s / 600s versions of one track.
- Make HPSS opt-in (`use_hpss`, default off). It was 91% of analysis time and
  did not change the estimate on any benchmark clip, synthetic or real.
- Halve the onset hop to 128 (`DEFAULT_TEMPO_HOP_LENGTH`). The old hop of 256
  quantised the tempogram badly enough to report 174 BPM as 170.5 and 160 as
  163.0; both are now correct.

Two correctness fixes fell out of the benchmarking:

- Silence reported a fabricated 70.2 BPM. A zero-energy onset envelope is
  finite, so it passed the guards and collapsed the weighted histogram onto its
  first bin. Windows below `MIN_ONSET_ENERGY` are now skipped, so silence
  returns `None`.
- Clips shorter than the 15s analysis window always returned `None`. They are
  now analysed as a single window down to `MIN_TEMPO_WINDOW_SECONDS`.

Still to verify: these timings are from the dev machine. The Raspberry Pi is
substantially slower, so the <10s budget should be re-measured on the cluster.


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
