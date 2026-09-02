## GenreFlow Frontend UI (FastAPI + static assets)

A minimal FastAPI service that serves a static drag-and-drop UI and forwards file uploads to the protected backend.

### Structure
- `frontend/app.py`: FastAPI app serving `index.html`, static assets, `/config.json`, and `/healthz`.
- `frontend/templates/index.html`: Single-page shell.
- `frontend/static/styles.css`: Simple styling with a bold look.
- `frontend/static/app.js`: Drag-and-drop logic and upload to `/predict/files`.

### Runtime config
- `GENREFLOW_API_BASE_URL`: Backend base URL. Defaults to `http://localhost:8080`.

### Local run
```bash
make frontend                      # or, manually:
cd frontend && uvicorn app:app --reload --port 3000
```
Visit `http://localhost:3000`, drop files, and the UI will POST to `${GENREFLOW_API_BASE_URL}/predict/files`.

### Kubernetes sketch
- Deploy backend as today (ClusterIP).
- Deploy this frontend as a separate Deployment + Service.
- Ingress routes only to the frontend Service. Frontend calls backend over the cluster DNS (`genreflow.local.backend.svc.cluster.local` or similar).
- Lock backend ingress behind auth/NW controls; keep CORS allowed for the frontend host only.

### Security notes
- Narrow `allow_origins` in the backend CORS middleware to the public UI domain.
- Consider a lightweight API token on the backend once public.
- Upload limits are enforced in the backend (50 MB per file, 20 files per batch);
  mirror the size cap at the ingress/reverse-proxy so oversized bodies are rejected earlier.
