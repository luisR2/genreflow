## GenreFlow Frontend UI (FastAPI + static assets)

A minimal FastAPI service that serves a static drag-and-drop UI and forwards file uploads to the protected backend.

### Structure
- `frontend/app.py`: serves `index.html`, static assets, `/healthz`, and proxies
  uploads to the backend at `POST /api/predict/{file,files}`.
- `frontend/templates/index.html`: Single-page shell.
- `frontend/static/styles.css`: Simple styling with a bold look.
- `frontend/static/app.js`: Drag-and-drop logic. Uploads one file per request to
  `/api/predict/file` and renders each result as it lands.

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
Visit `http://localhost:3000` and drop files. The UI sends one `POST
/api/predict/file` per file, which the service forwards to
`${GENREFLOW_API_BASE_URL}/predict/file`. Results appear one at a time, and a
file that fails gets a row explaining why rather than aborting the rest.

The bulk endpoint still exists for scripted callers, but the browser no longer
uses it: a single request carrying the whole selection is what runs into a
tunnel's body-size and origin-timeout limits.

### Kubernetes sketch
- Deploy backend as today (ClusterIP).
- Deploy this frontend as a separate Deployment + Service.
- Ingress routes only to the frontend Service. Frontend calls backend over the cluster DNS (`genreflow.local.backend.svc.cluster.local` or similar).
- The backend has no ingress at all; the frontend proxy is its only route in.

### Security notes
- The backend has no CORS middleware and needs none; all traffic is same-origin.
- Only `/predict/file` and `/predict/files` are proxyable. The allowlist in
  `PROXYABLE_PREDICT_PATHS` stops this becoming a general-purpose tunnel into
  the cluster.
- Consider a lightweight API token on the backend once public.
- Upload limits are enforced in the backend: 50 MB per file, 100 MB per request,
  8 files per batch. The per-file cap is applied while the body is read, so an
  oversized upload is abandoned rather than buffered, and `Content-Length` is
  checked in middleware before the multipart parser runs.
- The batch limit is derived from a measured Pi timing (~4.8 s per track) against
  the 100 s origin timeout a proxy typically enforces, not picked by feel.
- `app.js` also checks the 50 MB cap client-side purely to fail fast; the backend
  remains the authority.
