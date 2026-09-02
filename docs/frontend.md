## GenreFlow Frontend UI (FastAPI + static assets)

A minimal FastAPI service that serves a static drag-and-drop UI and forwards file uploads to the protected backend.

### Structure
- `frontend/app.py`: serves `index.html`, static assets, `/healthz`, and proxies
  uploads to the backend at `POST /api/predict/{file,files}`.
- `frontend/templates/index.html`: Single-page shell.
- `frontend/static/styles.css`: Simple styling with a bold look.
- `frontend/static/app.js`: Drag-and-drop logic and upload to `/predict/files`.

### Runtime config
- `GENREFLOW_API_BASE_URL`: Backend base URL the proxy forwards to. Defaults to
  `http://localhost:8080`. This is an **internal** address -- the browser never
  sees it, so it is never a public hostname.
- `GENREFLOW_UPSTREAM_TIMEOUT`: Proxy timeout in seconds. Defaults to `120`.

### Why the proxy
The browser used to upload straight to the backend, which forced the backend to
be publicly reachable and required CORS. Everything now goes through this
service's own origin, so the backend keeps a ClusterIP with no ingress, there is
one public hostname instead of two, and CORS is unnecessary.

### Local run
```bash
make frontend                      # or, manually:
cd frontend && uvicorn app:app --reload --port 3000
```
Visit `http://localhost:3000`, drop files, and the UI will POST to `/api/predict/files`,
which the service forwards to `${GENREFLOW_API_BASE_URL}/predict/files`.

### Kubernetes sketch
- Deploy backend as today (ClusterIP).
- Deploy this frontend as a separate Deployment + Service.
- Ingress routes only to the frontend Service. Frontend calls backend over the cluster DNS (`genreflow.local.backend.svc.cluster.local` or similar).
- Lock backend ingress behind auth/NW controls; keep CORS allowed for the frontend host only.

### Security notes
- The backend has no CORS middleware and needs none; all traffic is same-origin.
- Only `/predict/file` and `/predict/files` are proxyable. The allowlist in
  `PROXYABLE_PREDICT_PATHS` stops this becoming a general-purpose tunnel into
  the cluster.
- Consider a lightweight API token on the backend once public.
- Upload limits are enforced in the backend (50 MB per file, 20 files per batch);
  mirror the size cap at the ingress/reverse-proxy so oversized bodies are rejected earlier.
