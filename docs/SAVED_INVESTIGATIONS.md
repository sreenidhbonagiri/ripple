# Saved investigations

Metadata-only bookmarks (title, optional public note, sensor, cursor, window, source).
Measurements always load from existing `readings` / `readings_15m` tables.

## Public demo constraints

- Notes are **public plain text** — do not enter private data.
- Opaque `/?i=<id>` links are **not authentication**; there is no public edit/delete.
- Supported `source_id`: `battledim-ltown-zenodo-4017659` only.
- Windows must sit on the 5-minute grid, last 5 minutes–24 hours, include the cursor,
  and lie within available benchmark coverage (`MIN(ts)`–`MAX(ts)` on `readings`).

## Migration

Additive SQL: `backend/migrations/002_saved_investigations.sql` via `scripts/migrate.py`.
Does not re-import SCADA or alter hypertables beyond creating `saved_investigations`.

## Rate limiting (production path)

Forwarding chain:

1. Client → **Caddy** (TLS) → `127.0.0.1:8080`
2. **nginx** (frontend container) → `backend:8000`
3. **FastAPI**

nginx sets `X-Forwarded-For` with `$proxy_add_x_forwarded_for` (appends the immediate
peer) and `X-Real-IP` to `$remote_addr` (Caddy on loopback). Clients can put spoofed
addresses on the **left** of `X-Forwarded-For`.

FastAPI therefore **does not** use the leftmost `X-Forwarded-For` value. It walks from
the **right**, skips trusted proxy hops (`127.0.0.1`, `::1`), and rate-limits on the
first remaining hop.

Limits are **process-local** (per uvicorn worker; not shared across replicas). The
in-memory map is pruned on idle windows and hard-capped (`max_keys`) so key floods
cannot grow without bound.
