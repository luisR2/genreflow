# GenreFlow Go-Live Plan

Ordered runbook for putting GenreFlow on the public internet, via **Cloudflare
Tunnel** onto the k3s Raspberry Pi cluster.

Work top to bottom. Phase 1 needs no cluster; Phases 2–5 do.

> Supersedes the DNS/TLS and ingress-hardening sections of
> [`frontend-public-exposure.md`](./frontend-public-exposure.md), which assumed
> port-forwarding with Let's Encrypt. Its goals, auth and secrets sections still
> apply. The tunnel means **no inbound ports and no cert-manager**: TLS
> terminates at Cloudflare and `cloudflared` dials out from inside the cluster.

---

## Constraints that shape everything below

Two Cloudflare limits conflict with the current upload settings. Decide these
before writing code, because they set the batch and file caps.

| Constraint | Value | Consequence |
|---|---|---|
| Max request body (Free/Pro) | **100 MB** | Current caps allow `20 × 50 MB = 1 GB` per request. Cloudflare rejects the request long before the backend sees it. |
| Origin response timeout | **100 s** (error 524) | A 20-file batch on a Pi can exceed this. Enterprise can raise it to 600 s; Free cannot. |

Analysis is ~0.6 s/track on a dev laptop. **Measured on the Pi (item 1.4): ~4.8 s
worst case per track**, plus a one-off ~12 s JIT warm-up per pod.

That lands almost exactly on the bad case the earlier draft guessed at: a 20-file
batch is **~96 s of CPU work against a 100 s timeout**, before counting warm-up
or any concurrency the 2-CPU limit cannot deliver. There is no headroom.

**Implication:** the current bulk endpoint is the wrong shape for a tunnel —
now confirmed by measurement, not assumed. Uploading files one request at a time
sidesteps both limits and lets results stream in progressively. See item 1.3.

---

## Phase 0 — Decisions

- [x] Exposure method: **Cloudflare Tunnel** (no inbound ports, no static IP)
- [x] TLS: terminated by Cloudflare; no cert-manager needed
- [ ] Domain registered and added to Cloudflare
- [ ] Hostname chosen (e.g. `genreflow.example.com`)
- [ ] Decide: fully public, or gated behind Cloudflare Access while testing?
      *Recommended: Access-gated for the first week, then open up.*

---

## Phase 1 — Code changes (no cluster required)

### 1.1 Proxy the backend through the frontend — **blocker**

Today `frontend/static/app.js:96` uploads from the browser straight to
`${apiBaseUrl}/predict/files`, and `k8s/base/frontend/deployment.yaml:39` sets
that base URL to `http://genreflow.local`. A visitor's browser cannot resolve a
cluster-internal name, so **the app would not work for anyone but you**.

It also forces the backend to be public, which contradicts the stated goal of
keeping it private.

- [x] Add a proxy route to `frontend/app.py`: `POST /api/predict/{file,files}`
      forwards to the backend over ClusterIP, streaming the body rather than
      buffering it, with an allowlist so it cannot proxy anything else
- [x] Point `app.js` at same-origin `/api/...`; drop `apiBaseUrl` and
      `/config.json`, which existed only to hand the browser a backend URL
- [x] Change `GENREFLOW_API_BASE_URL` to the in-cluster service DNS
      (`http://genreflow-backend.genreflow-backend.svc.cluster.local`)
- [x] Delete `k8s/base/backend/ingress.yaml` — the backend needs no ingress
- [x] Remove the CORS middleware from `backend/app/app.py`; same-origin requests
      don't need it, and it stops being a thing to get wrong

**Done** — 19 tests in `backend/tests/test_frontend_proxy.py` cover forwarding,
error relaying (400/413/415/500 pass through with their detail), 502/504 on an
unreachable or slow backend, and rejection of non-allowlisted paths.

**Why it's worth doing first:** one public hostname instead of two, no CORS, no
backend ingress to harden, and the tunnel config gets a single service.

**Verify:** `make compose-up`, then upload through the UI with the backend port
*not* published to the host — it should still work.

### 1.2 Enforce the upload cap before reading the file — **security**, done

`backend/app/routes_file.py:97` does `data = await file.read()` and only then
calls `_validate_audio_file`. The whole upload is resident before the 50 MB
check runs. With `asyncio.gather` over a batch, one unauthenticated request can
pull ~1 GB into a pod limited to 2000Mi and OOM-kill it.

- [x] Reject on `Content-Length` before reading — in HTTP middleware, so it runs
      ahead of Starlette's multipart parser rather than after it has already
      spooled every part to disk
- [x] Stream the body and abort once the cap is exceeded, rather than buffering
- [x] Keep the existing magic-byte check on the streamed prefix — it now runs on
      the first 8 KB, so non-audio is refused with 415 after ~8 KB instead of
      after a full 50 MB
- [x] Share one byte budget across a batch, so `asyncio.gather` cannot let each
      file buffer `MAX_FILE_SIZE_BYTES` at the same time

**Verified.** A 200 MB chunked upload against a live backend, measuring the
server process's RSS:

| | Response | Peak RSS delta |
|---|---|---|
| Before | 413 | **143 MB** |
| After | 413 | **53 MB** |

Both answer 413; only the new path declines to hold the upload while deciding.
53 MB is the 50 MB per-file cap plus framing overhead, as intended.

**Note:** `MAX_REQUEST_BYTES` is 100 MB, matching Cloudflare's Free/Pro body
limit. Item 1.3 reconciled this with the batch size, which is now 8.

### 1.3 Reshape the batch endpoint for the tunnel — **done**

- [x] Decided: **per-file requests** from the frontend. It removes the 100 s
      timeout and 100 MB body risks outright rather than managing them, and no
      single request has to carry a whole selection however many files are queued
- [x] `app.js` uploads sequentially and renders each result as it lands. A file
      that fails gets its own row with the reason instead of aborting the run,
      and the 50 MB cap is mirrored client-side purely to fail fast
- [x] `MAX_BATCH_SIZE` 20 → **8**, derived from the measured ~4.8 s/track: eight
      tracks is ~38 s against the 100 s ceiling, where twenty was ~96 s. The bulk
      endpoint now only bounds scripted callers; the browser does not use it

**Verified** end-to-end against a live backend and frontend, uploading through
the proxy:

    a_90.wav     status 200  bpm 90.4   truth 90.0
    b_128.wav    status 200  bpm 127.1  truth 128.0
    c_174.wav    status 200  bpm 174.4  truth 174.0
    60 MB file   status 413  File too large. Maximum allowed size is 50 MB.
    non-audio    status 415  File content does not appear to be a supported audio format
    9 files      status 413  Too many files. Maximum batch size is 8.

This also resolves the 100 MB / 20-file conflict item 1.2 left open.

### 1.4 Measure on the Pi — **done 2026-09-04**

Measured in the backend pod on `k8s-node2` (Raspberry Pi 4 Model B, 4 cores,
container limited to 2 CPU / 2000Mi), running current `main` code:

| Clip | Analysis time |
|---|---|
| 30 s audio | ~2.0 s |
| 180 s audio | ~4.4 s |
| 300 s audio | ~4.4 s |

- [x] Run `make bench` on a cluster node; record the worst case
- [x] Steady-state worst case is **~4.8 s/track**, comfortably inside the 10 s
      budget. `DEFAULT_MAX_ANALYSIS_SECONDS` does **not** need revisiting.
- [x] The 60 s excerpt cap holds on real hardware: 180 s and 300 s tracks take
      the same time, so runtime is flat with track length as intended.

**New finding — cold start costs ~12 s.** The first analysis after a pod starts
takes **~15.5 s**; every call after it takes ~3.2 s, with identical input:

    call 1:  15.50s  bpm=129.3
    call 2:   3.24s  bpm=129.3
    call 3:   3.25s  bpm=129.3
    call 4:   3.23s  bpm=129.3

This is librosa's numba JIT compiling on first use. It is one-off per process,
but it means the first visitor after any deploy, restart or scale-up waits ~15 s
— and it is the only measured case that breaks the 10 s budget.

- [ ] Warm the JIT during `lifespan` by analysing a short synthetic clip at
      startup, so the cost lands before the pod reports ready rather than on a
      user. Keep it behind the readiness probe.

### 1.5 Security headers

- [ ] Add CSP, `X-Content-Type-Options: nosniff`, `Referrer-Policy`, and
      `X-Frame-Options: DENY` to frontend responses
- [ ] Confirm the frontend still has `docs_url=None` (it does — `frontend/app.py:22`)
- [ ] Decide whether the **backend** should keep `/docs`, `/redoc` and
      `/openapi.json` enabled (`backend/app/app.py:33-35`). Behind the proxy they
      are unreachable publicly; disable them anyway if you want defence in depth.

---

## Phase 2 — Manifests

### 2.1 Pin image tags — **GitOps correctness**, done

Both deployments use `:latest` with `imagePullPolicy: Always`
(`k8s/base/backend/deployment.yaml:44`, `k8s/base/frontend/deployment.yaml:36`).
CI already builds a SHA tag (`${GITHUB_SHA::7}`) and never uses it.

With `latest`: ArgoCD sees no spec change when you ship, so it isn't tracking
what actually runs; you cannot roll back; and two pods of the same Deployment
can silently run different code after a restart.

- [x] Set the image tag in the overlay via a kustomize `images:` block
- [x] Have CI bump that tag and commit — a "Pin image tag in the overlays" step
      rewrites `newTag` after the build and pushes with `[skip ci]`, so the
      commit ArgoCD syncs names the image that was actually built
- [x] Drop `imagePullPolicy: Always` — now `IfNotPresent`, since SHA tags are
      immutable and there is nothing to re-pull

### 2.2 Harden the pods — done and smoke-tested

- [x] `readOnlyRootFilesystem: true` on both containers, with an `emptyDir` at
      `/tmp`. The emptyDir uses `medium: Memory`, which also keeps Starlette's
      multipart spooling off the nodes' SD cards — a real concern, since every
      upload over 1 MB is written to a temp file and the cards wear out
- [x] Point everything that writes at that tmpfs: `TMPDIR`, `HOME`,
      `NUMBA_CACHE_DIR`, `MPLCONFIGDIR`, `XDG_CACHE_HOME`, plus
      `PYTHONDONTWRITEBYTECODE=1` since site-packages is no longer writable.
      numba is the one that matters — librosa JIT-compiles through it
- [x] Add a CPU limit to the frontend: `500m`. It had memory only, so it could
      compete with the analyser for CPU
- [x] Add `automountServiceAccountToken: false` on both
- [x] `replicas: 2` on the frontend, with soft pod anti-affinity so the two do
      not land on the same node

**Smoke-tested on the cluster (2026-09-10).** Both images were run as throwaway
pods on a real node with the hardened `securityContext` before this was pushed,
because `readOnlyRootFilesystem` is the one change here that can crashloop a pod
and ArgoCD syncs with `automated.selfHeal`.

Backend, on `k8s-node3`:

    healthz: 200   readyz: 200
    analyse 1: status=200 wall=  6.53s -> bpm 127.1
    analyse 2: status=200 wall=  0.71s -> bpm 127.1
    analyse 3: status=200 wall=  0.71s -> bpm 127.1
    non-audio: 415
    numba cache files: 52

Those 52 files are the point: numba really does write a cache at runtime, and
without `NUMBA_CACHE_DIR` pointed at the tmpfs it would have been writing to a
read-only path. The 6.53 s → 0.71 s step is the JIT warm-up from item 1.4,
visible again.

Frontend:

    healthz 200, index 200, app.js per-file: True, bulk call absent: True
    proxy -> backend: 200 -> bpm 127.1
    non-allowlisted path: 404

One trap worth recording: the test pod reported `Ready` while nothing was
listening, because a bare pod has no probes. The real Deployment's
`startupProbe` (`failureThreshold: 18`, ~3 min) exists precisely because
importing librosa on a Pi is slow. Do not read `Ready` on a probe-less pod as
"the app is up".

### 2.3 Ingress

- [x] Delete the backend ingress — done in 1.1
- [x] Keep the frontend ingress internal — documented on the manifest: plain HTTP
      on the `web` entrypoint, no `websecure`, no port opened at the router
- [ ] Set the ingress host to the real hostname so Traefik routes tunnel traffic.
      **Blocked on Phase 0** — the domain is not registered yet, so the host is
      still `ui.genreflow.local` with a TODO on it

---

## Phase 3 — Cloudflare

- [ ] Create the tunnel: `cloudflared tunnel create genreflow`
- [ ] Store the tunnel credentials as a **SealedSecret** (same pattern as the
      Docker Hub secret — see [`maintenance.md`](./maintenance.md))
- [ ] Deploy `cloudflared` in-cluster (Deployment, 2 replicas for HA), with
      ingress rules pointing at the frontend Service
- [ ] Add the DNS record: `cloudflared tunnel route dns genreflow <hostname>`
- [ ] **WAF / rate limiting** — the app has no auth and does CPU-heavy work on a
      Pi. Add a rate-limit rule on the upload path (start strict, e.g. 10 req/min
      per IP, and loosen with evidence)
- [ ] Set "Under Attack" mode as a known escape hatch
- [ ] Optional but recommended for launch week: **Cloudflare Access** in front of
      the hostname, so only invited emails can reach it

---

## Phase 4 — Validation

Run against the public hostname before announcing it.

**Function**
- [ ] Upload one file — correct BPM returned
- [ ] Upload the max batch — completes under the 100 s timeout
- [ ] Results render; errors surface in the UI rather than failing silently

**Limits**
- [ ] File over the cap → 413, and the pod does not spike in memory
- [ ] Batch over the cap → 413
- [ ] A ~150 MB upload → rejected by Cloudflare, and the UI shows something sane
- [ ] Non-audio file renamed `.wav` → 415 (magic-byte check)

**Exposure**
- [ ] `curl` the backend Service from outside → unreachable
- [ ] k3s API (6443) and Argo CD → not reachable from the internet
- [ ] Router shows **no** inbound port-forward rules
- [ ] `https://<host>` serves valid TLS; HTTP redirects
- [ ] Node SSH not exposed publicly

**Load**
- [ ] Several concurrent uploads — the Pi stays responsive and pods don't OOM
- [ ] Confirm what a rate-limited client actually sees

---

## Phase 5 — Day-2

- [ ] Alert on pod restarts, OOM kills, and 5xx rate
- [ ] Watch Cloudflare analytics for abuse in week one
- [ ] Back up the SealedSecrets private key from `kube-system` — without it, no
      secret in this repo can be decrypted after a cluster rebuild
- [ ] Document a rollback: revert the image tag in the overlay, let ArgoCD sync
- [ ] Trivy already runs in CI; act on findings before launch

---

## Suggested order

1. ~~**1.1** proxy refactor~~ — done (`ca7a434`)
2. ~~**1.4** measure on the Pi~~ — done 2026-09-04; ~4.8 s/track, ~12 s cold start
3. ~~**1.2** upload cap~~ — done; 200 MB upload now costs 53 MB RSS, was 143 MB
4. ~~**1.3** batch reshaping~~ — done; per-file uploads, batch capped at 8
5. ~~**2.x** manifests~~ — 2.1 and 2.2 done; 2.3 waits on the hostname
6. **3** tunnel, Access-gated
7. **4** validation, then remove the gate

Items 1.1–1.3 and 2.x are code and manifests, doable without the cluster.
