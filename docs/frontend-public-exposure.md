# Public Frontend Exposure Plan (k3s on Raspberry Pi)

Secure steps to expose the GenreFlow UI to the internet while keeping the Pi cluster and backend safe.

## Goals
- Public HTTPS endpoint for the frontend.
- Keep Kubernetes API and Argo CD private.
- Keep the backend API non-public (or gated) and only reachable via the frontend domain.
- Add basic protections (TLS, rate limiting, auth, logging).

## Architecture
- Public ingress for `ui.yourdomain.com` -> frontend Service (`genreflow-frontend`).
- Backend stays ClusterIP. If internet access is required, expose via `api.yourdomain.com` but gate it with auth/rate limits; otherwise do not publish it.
- Frontend calls backend through the public API host, or through ClusterIP if both run inside the cluster.
- Do not expose the k3s API server or Argo CD UI; reach them via VPN or SSH tunnel only.

## DNS + TLS
- Use an A/AAAA (static IP) or Cloudflare/Route53 proxied record for `ui.yourdomain.com` (and `api.yourdomain.com` if needed).
- Terminate TLS with Let’s Encrypt via Traefik’s ACME or cert-manager. Enforce HTTPS-only and HSTS.
- If you have dynamic IP, use DDNS or Cloudflare Tunnel to avoid inbound open ports.

## Ingress hardening (Traefik examples)
- Enable entrypoint `websecure` only; redirect HTTP -> HTTPS.
- Middlewares:
  - `redirectscheme` for HTTPS-only.
  - `ratelimit` to cap requests (e.g., 50 req/s burst 100).
  - `buffers`/`maxBodyBytes` to cap upload size.
  - `ipwhitelist` or `forwardauth` for the backend if you must expose it.
- Example host rules:
  - Frontend: `Host("ui.yourdomain.com")` -> Service `genreflow-frontend`.
  - Backend (optional/public): `Host("api.yourdomain.com") && PathPrefix("/predict")` -> Service `genreflow`.

## Auth and access options
- Best: keep backend private; only the frontend domain is public. Frontend talks to backend via ingress host that is not published in DNS.
- If backend must be public:
  - Add OIDC login (Auth0/Keycloak) at the ingress using forward auth.
  - Or Cloudflare Access in front of `api.yourdomain.com`.
  - At minimum, basic auth + rate limit + IP allowlist.
- Restrict backend CORS to the frontend origin(s) only.

## Network and node safety
- Firewall: only 80/443 to the ingress. Block 6443 (k3s API) and any node SSH from the internet; use VPN or bastion.
- Optionally add NetworkPolicies to limit pod-to-pod traffic (depends on CNI support).
- Keep ingress controller and nodes updated; enable minimal privileges in pod securityContext.

## Secrets and supply chain
- Continue using SealedSecrets for DockerHub and any API keys.
- Rotate credentials before going public; enable image pull secrets per namespace.
- Consider signing images (cosign) and scanning (Trivy) in CI.

## Observability and ops
- Enable ingress/access logs and basic dashboards (Prometheus/Grafana if available).
- Configure alerts for high error rate, 429/5xx spikes, and TLS renewal failures.
- Back up the SealedSecrets private key (from `kube-system`).

## Suggested rollout checklist
1) Pick domain and set DNS for `ui.yourdomain.com` (and `api.yourdomain.com` if needed).
2) Configure Traefik ACME (or install cert-manager) for TLS with HTTP->HTTPS redirect.
3) Add middlewares: rate limit, upload size caps, HTTPS redirect; apply to frontend ingress.
4) Keep backend non-public; if required, expose it with auth + rate limit + IP allowlist.
5) Update `GENREFLOW_API_BASE_URL` to the public backend host (or internal ClusterIP if you keep backend private).
6) Tighten backend CORS to the frontend origin.
7) Lock down k3s API and Argo CD behind VPN/tunnel; remove any public exposure.
8) Validate: TLS issued, redirects enforced, rate limits working, uploads within size caps, backend not directly reachable without auth.
