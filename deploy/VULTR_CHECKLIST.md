# Vultr deployment checklist (prepare only — do not provision yet)

Ripple is a historical investigation workspace. Do not present it as live leak detection.

## Before creating any Vultr resources

- [ ] Confirm Tiger Cloud `DATABASE_URL` and `RIPPLE_STORAGE_LIMIT_BYTES` (Console size; no default).
- [ ] Confirm `artifacts/january_raw_cagg_benchmark.json` is present for the Tiger evidence panel.
- [ ] Confirm `data/L-TOWN.inp` is available to the backend image build context.
- [ ] Decide region, instance size, and whether to use Docker on a single VM vs managed containers.
- [ ] Plan secrets: inject `DATABASE_URL` / storage limit at **runtime** only (env file on host, Vultr secrets, or orchestrator env). Never commit `.env` or bake credentials into images.

## Suggested single-VM Docker path (later)

1. Create a Vultr cloud compute instance (Ubuntu LTS) — **not done in this milestone**.
2. Install Docker Engine + Compose plugin.
3. Copy the repo (or pull from git) to the host; place runtime `.env` with `DATABASE_URL` and `RIPPLE_STORAGE_LIMIT_BYTES` only (mode `600`).
4. Set `RIPPLE_CORS_ORIGINS` to the public frontend origin(s).
5. Build and start: `docker compose up -d --build`.
6. Open firewall for `80` (frontend) or put TLS terminator (Caddy/nginx) in front; keep `8000` private if proxied.
7. Verify:
   - `GET /api/health` → liveness
   - `GET /api/ready` → database reachable (no secrets in body)
   - `GET /healthz` on frontend → ok
   - Jan 12 preset + Tiger panel (expand) loads saved benchmark without re-running timings

## Health checks

| Endpoint | Purpose |
|----------|---------|
| `GET /api/health` | Process up (no DB) |
| `GET /api/ready` | DB configured and reachable |
| `GET /healthz` (frontend container) | nginx up |

Compose already wires container healthchecks to these.

## Do not

- Provision Vultr instances, DNS, or load balancers from this checklist yet
- Upgrade Tiger storage or import additional SCADA months during deploy prep
- Expose database credentials in logs, UI, or image layers
