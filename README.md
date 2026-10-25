# Ripple

**Live:** [https://followtheripple.us](https://followtheripple.us)

Historical water-network investigation workspace for the official [BattLeDIM](https://battledim.ucy.ac.cy/) L-Town benchmark ([Zenodo 4017659](https://zenodo.org/records/4017659)).

**Problem.** Water utilities and researchers need a way to replay historical SCADA, inspect synchronized sensor evidence, and share findings without treating model scores as confirmed leaks or pipe localizations.

**Product boundaries**

- Historical benchmark replay — not live utility monitoring
- Pressure anomalies and experimental warnings are **not** confirmed leaks
- No predicted leak-pipe rankings / no localization claims
- Observations after the replay cursor are never exposed

**Sponsor targets:** Best Use of Tiger Data (primary); Vultr deployment (secondary).

## Current features

- Network map + cursor-safe SCADA replay (5-minute BattLeDIM clock)
- Selected-sensor pressure chart, 30-minute observation deltas, inflow / pump / tank context
- Hourly pressure history from Timescale continuous aggregates (`readings_15m`)
- **Experimental Method M** anomaly warning (frozen **five-minute** scoring, January 2019 serving artifact) — investigation support only
- Save / reopen investigation **metadata** (public notes; share via `/?i=<id>`)
- Tiger Data evidence panel (live size/counts + **saved** January raw-vs-CAGG timings; lazy; no re-bench on load)

## Architecture (short)

| Layer | Role |
|-------|------|
| Frontend | React + Cytoscape + ECharts; same-origin `/api` in Docker |
| Backend | FastAPI; cursor-safe reads; Method M warning from file-backed January artifact (optional Tiger store) |
| Tiger Data | Hypertables for raw SCADA; continuous aggregates for historical context; relational metadata for saved investigations; optional frozen Method M evidence (`003`) |
| Deploy | Docker Compose on Vultr; Caddy TLS at `followtheripple.us` |

## Evaluation limitations (Method M)

Diagnostic **2019** research evaluation of frozen five-minute Method M (not a blind holdout; not real-utility validation):

| Metric | Value |
|--------|------:|
| Primary abrupt recall (excl. development example **p523**) | **2/8** |
| Inclusive abrupt recall | **3/9** |
| Incipient recall | **0/10** |
| Unmatched notifications (2019) | **6** |

Same detected abrupt events as hourly Method M on shared hits, with earlier notifies where the five-minute grid allows. **No localization or operational-savings claims.**

## Demo scripts

- Presenter walkthrough (Tiger + Jan 12 observation): [`docs/PRESENTER_90S.md`](docs/PRESENTER_90S.md)
- **Experimental Method M warning demo:** [`docs/METHOD_M_WARNING_DEMO.md`](docs/METHOD_M_WARNING_DEMO.md)
- **Method M in Tiger (optional, local verify first):** [`docs/METHOD_M_TIGER.md`](docs/METHOD_M_TIGER.md)

Loading metrics: [`docs/LOADING_PERFORMANCE.md`](docs/LOADING_PERFORMANCE.md). Deploy: [`deploy/VULTR_CHECKLIST.md`](deploy/VULTR_CHECKLIST.md), `docker-compose.yml`. HTTPS: [`docs/HTTPS_CADDY.md`](docs/HTTPS_CADDY.md).

## Requirements

- Python 3.12
- Node.js 20+ (npm)
- `curl`
- Tiger Cloud / TimescaleDB (`DATABASE_URL` in project-root `.env`)

## Setup

### 1. Environment

```bash
cp .env.example .env
# Set DATABASE_URL for Tiger Cloud (never commit .env)
# Set RIPPLE_STORAGE_LIMIT_BYTES from Tiger Console (required before imports)
```

**Storage capacity (imports):** `RIPPLE_STORAGE_LIMIT_BYTES` must be set explicitly (Tiger Console service size). There is no default fallback. Working ceiling = 80% of that limit (20% headroom). Free tier example: limit `786432000` (750 MiB) → ceiling `629145600` (600 MiB). Imports estimate projected `pg_database_size` (tables, indexes, continuous aggregates) and refuse if the projection exceeds the working ceiling.

### 2. Download official data

```bash
chmod +x scripts/download_ltown.sh scripts/download_scada_2019.sh
./scripts/download_ltown.sh
./scripts/download_scada_2019.sh
```

- `L-TOWN.inp` — nominal model (not `L-TOWN_Real.inp`)
- `2019_SCADA_Pressures.csv`, `2019_SCADA_Flows.csv`, `2019_SCADA_Levels.csv`
- `dataset_configuration.yaml` (sensor lists only are used; leak labels are excluded from the app data flow)

SCADA CSVs use **semicolon** delimiters and **decimal commas**. Units: pressure `m`, flow `m³/h`, tank level `m`.

### 3. Backend + migrate + small import

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt

# schema + hypertable + readings_15m CAGG (WITH NO DATA)
python scripts/migrate.py

# Presenter-sized window (default) or expanded historical range:
python scripts/import_scada_window.py
python scripts/import_scada_window.py \
  --start "2019-01-01 00:00:00" --end "2019-02-01 00:00:00" --end-exclusive

cd backend
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### 4. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open [http://127.0.0.1:5173](http://127.0.0.1:5173). Production: [https://followtheripple.us](https://followtheripple.us).

## Freshness rule (5-minute SCADA)

At cursor `T`, each sensor uses the latest **raw** reading with `ts <= T` (never CAGG buckets, never `ts > T`):

| Status | Rule |
|--------|------|
| `current` | `age_seconds <= 300` |
| `stale` | observation exists and `age_seconds > 300` |
| `missing` | no reading at or before `T` |

## API

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | Health + product boundary |
| `GET` | `/api/network` | Parsed EPANET topology |
| `GET` | `/api/sensors` | Sensor catalog |
| `GET` | `/api/sensors/{id}/readings?start=&end=` | Bounded raw series (capped) |
| `GET` | `/api/replay/window` | Imported replay bounds |
| `GET` | `/api/replay/snapshot?at=` | Cursor snapshot (raw, `ts <= at`) |
| `GET` | `/api/investigation/pressure-change?at=&sensor_id=` | 30-minute pressure observation delta (unavailable if missing/stale; not a leak claim) |
| `GET` | `/api/sensors/{id}/hourly-history?at=&days=` | Hourly pressure context from `readings_15m` (≤30 days before cursor; bucket_end ≤ cursor) |
| `GET` | `/api/presenter/preset` | Jan 12 illustrative bookmarks (not alerts/leaks) |
| `GET` | `/api/experimental/method-m-warning?at=` | Cursor-safe Experimental Method M warning (January five-minute artifact) |
| `GET` | `/api/experimental/method-m-timeline?at=` | Preceding-24h Method M score timeline from Tiger (requires `RIPPLE_METHOD_M_STORE=tiger`) |
| `GET` | `/api/tiger/evidence` | Live counts/size + **saved** January raw/CAGG artifact (lazy; no re-bench) |
| `POST` | `/api/investigations` | Save investigation **metadata** (public notes; rate-limited; no edit/delete) |
| `GET` | `/api/investigations/{id}` | Reopen saved metadata; measurements still come from time-series APIs |
| `GET` | `/api/ready` | Readiness (DB reachable); `/api/health` stays liveness-only |

Saved investigations store title/note/sensor/cursor/window/source only. Share via `/?i=<opaque_id>` (not authentication). Notes are public plain text — do not enter private data. Migration `002_saved_investigations.sql` must be applied before Tiger-backed saves (not auto-run on deploy). Details: [`docs/SAVED_INVESTIGATIONS.md`](docs/SAVED_INVESTIGATIONS.md).

`/api/replay/window` returns **presenter** playback bounds (Jan 12 14:00–17:00) plus separate **data_start/data_end** database coverage. Coverage `reading_count` is Timescale **estimated** (`reading_count_estimated`); exact totals stay on `/api/tiger/evidence`.

Timestamps are **TIMESTAMP WITHOUT TIME ZONE** (naive BattLeDIM clock). Do not attach a geographic timezone.

## Docker (local, verified)

Requires **Docker Desktop/Engine running** (not just the CLI). Uses the existing Tiger Cloud database; does **not** migrate or import on startup.

```bash
./scripts/download_ltown.sh   # MD5 bfbb16b8b463e0576200ba6ad360f68e
# .env must define DATABASE_URL and RIPPLE_STORAGE_LIMIT_BYTES (runtime only)
docker compose build
docker compose up -d          # http://127.0.0.1:8080 — backend unpublished
docker compose down
```

Frontend assets call same-origin `/api` (nginx → internal backend). Keep Vite `:5173` / uvicorn `:8000` for development if needed.

## Verification helpers

```bash
source .venv/bin/activate
python -m pytest backend/tests -q
# January-only raw vs readings_15m CAGG (7× alternating; no import)
python scripts/benchmark_january_raw_cagg.py
cd frontend && npm run typecheck && npm run build
```

## Layout

```
backend/            FastAPI + WNTR + psycopg
backend/migrations/ Repeatable SQL migrations
frontend/           React + TypeScript + Vite + Cytoscape + ECharts
scripts/            Download, migrate, import, connection verify
data/               Local benchmark files (gitignored)
.env.example        Placeholder env vars (no credentials)
```

## Notes

- Do not commit raw datasets, virtualenvs, `node_modules`, build outputs, or secret `.env` files.
- Milestone 2 imports only the small window above — not the full 2019 year.
- Leak ground-truth files are not downloaded or processed by the product data flow.
