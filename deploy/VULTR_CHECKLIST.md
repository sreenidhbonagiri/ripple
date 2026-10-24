# Docker deployment checklist (local verified → Vultr next)

Ripple is a historical investigation workspace. Do not present it as live leak detection.

## Local Docker — verified on this machine

**Prerequisites**

- Docker Desktop (or Engine) running — CLI alone is not enough
- Docker Compose plugin
- Project-root `.env` with `DATABASE_URL` and `RIPPLE_STORAGE_LIMIT_BYTES` (never commit)
- Official nominal model downloaded and checksum-verified

**Setup / start / stop**

```bash
# 1) Official L-TOWN.inp (MD5 bfbb16b8b463e0576200ba6ad360f68e)
chmod +x scripts/download_ltown.sh
./scripts/download_ltown.sh

# 2) Build images (WNTR compiles in backend image; no secrets baked in)
docker compose build

# 3) Start — publishes frontend only on :8080; backend stays internal
docker compose up -d

# 4) Stop
docker compose down
```

Open **http://127.0.0.1:8080/** (Vite :5173 and local uvicorn :8000 can keep running separately).

**Verified behavior (actual run)**

| Check | Result |
|-------|--------|
| `GET http://127.0.0.1:8080/healthz` | 200 `ok` |
| `GET http://127.0.0.1:8080/api/health` via nginx | 200 |
| `GET http://127.0.0.1:8080/api/ready` via nginx | 200 `database=ok` |
| Backend host port | **not published** (`8000/tcp` internal only) |
| `L-TOWN.inp` in container | bind-mounted; MD5 matches Zenodo nominal |
| Network map | 785 nodes · 909 links · 37 sensors |
| Jan 12 illustrative preset (n54 @ 15:00) | −0.95 m; inflows / PUMP_1 / T1 coordinated |
| Hourly history | no post-cursor hours |
| Tiger evidence | saved artifact; `reran_expensive_benchmark=false` |
| Frontend assets | no `localhost:8000` / no `DATABASE_URL` |
| Backend logs | no postgres URL / password patterns |
| `docker compose restart backend` | recovers to healthy; `/api/ready` 200 |
| Startup | **no** migrate/import |

**Design notes that matched verification**

- `DATABASE_URL` injected at **runtime** into the backend service only
- `.dockerignore` excludes `.env`, `data/` (SCADA), venvs; INP is mounted, not copied into layers
- Frontend build sets `VITE_API_BASE_URL=` so the browser uses same-origin `/api` (nginx → `backend:8000`)
- Compose does not run migrations or SCADA imports
- Frontend listens on host **`:8080`** → container `:80`; backend has **no published host port**
- Model path: host `./data/L-TOWN.inp` bind-mounted read-only to `/app/data/L-TOWN.inp` (download via `scripts/download_ltown.sh`, MD5 `bfbb16b8b463e0576200ba6ad360f68e`)

**Platform note (arm64 host vs amd64 Vultr)**

- Local **runtime** verification used **linux/arm64** images on Docker Desktop (Apple Silicon).
- Typical Vultr VMs are **linux/amd64**. Prefer `docker compose build` on the VM, or `docker buildx build --platform linux/amd64`.
- Pre-push check on this machine (buildx, **image build only — not runtime**):
  - `Dockerfile.backend` → `linux/amd64` **succeeded** (WNTR/`numpy`/`scipy` via manylinux x86_64 wheels)
  - `Dockerfile.frontend` → `linux/amd64` **succeeded**
- Backend Dockerfile still includes compilers for arches without wheels (observed: arm64 compiled WNTR from source).
- **Image-build success ≠ runtime verification** on Vultr — re-check `/api/ready`, map, Jan 12 preset, and Tiger panel after deploy.

## Before creating any Vultr resources

- [x] Local `docker compose build` + `up` verified (this checklist)
- [ ] Confirm Tiger Cloud `DATABASE_URL` and `RIPPLE_STORAGE_LIMIT_BYTES` for the target host `.env` (mode `600`)
- [ ] Confirm `artifacts/january_raw_cagg_benchmark.json` is present in the repo checkout used to build
- [ ] Run `./scripts/download_ltown.sh` on the host (or copy the verified INP) before `compose up`
- [ ] Decide region, instance size, and single-VM Docker vs managed containers
- [ ] Set `RIPPLE_CORS_ORIGINS` to the public frontend origin(s) if the UI is not same-origin with the API proxy
- [ ] Plan TLS (Caddy/nginx) in front of published port 80/443; do **not** publish backend 8000
- [ ] HTTPS runbook: [`docs/HTTPS_CADDY.md`](../docs/HTTPS_CADDY.md) (`deploy/Caddyfile`, `deploy/docker-compose.caddy.yml`)

## Suggested single-VM Docker path (later — not provisioned yet)

1. Create a Vultr cloud compute instance (Ubuntu LTS).
2. Install Docker Engine + Compose plugin.
3. Copy/clone the repo; place runtime `.env` with `DATABASE_URL` + `RIPPLE_STORAGE_LIMIT_BYTES` only.
4. `./scripts/download_ltown.sh` then `docker compose up -d --build`.
5. Open firewall for the frontend (80/443); keep backend unpublished.
6. Re-run the local verification table against the public URL.

## Health checks

| Endpoint | Purpose |
|----------|---------|
| `GET /api/health` | Process up (no DB) |
| `GET /api/ready` | DB configured and reachable |
| `GET /healthz` (frontend container) | nginx up |

Compose wires container healthchecks to these. Frontend waits until backend is healthy.

## Do not

- Provision Vultr instances, DNS, or load balancers from this checklist yet
- Upgrade Tiger storage or import additional SCADA months during deploy
- Bake credentials into images or commit `.env`
- Expose database credentials in logs, UI, or image layers
