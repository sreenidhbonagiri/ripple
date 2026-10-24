# Ripple

Historical water-network investigation workspace for the official [BattLeDIM](https://battledim.ucy.ac.cy/) L-Town benchmark ([Zenodo 4017659](https://zenodo.org/records/4017659)).

**Product boundaries**

- Historical benchmark replay — not live utility monitoring
- Pressure anomalies are not confirmed leaks
- No predicted leak-pipe rankings
- Observations after the replay cursor are never exposed

**Sponsor targets:** Best Use of Tiger Data (primary); Vultr deployment (secondary).

**Current scope:** Milestones 1–5 (network viewer, Tiger storage/replay, investigation evidence, historical pressure context, sponsor evidence / presenter readiness). No detection.

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

Open [http://127.0.0.1:5173](http://127.0.0.1:5173).

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
| `GET` | `/api/tiger/evidence` | Live counts/size + **saved** January raw/CAGG artifact (lazy; no re-bench) |
| `GET` | `/api/ready` | Readiness (DB reachable); `/api/health` stays liveness-only |

`/api/replay/window` returns **presenter** playback bounds (Jan 12 14:00–17:00) plus separate **data_start/data_end** database coverage.

Presenter UI: Jan 12 preset buttons + illustrative sensor **n54** at **15:00** (verified fresh 30-minute pressure drop — observation only). Tiger panel loads evidence on expand.

Demo script: [`docs/PRESENTER_90S.md`](docs/PRESENTER_90S.md). Deploy prep: [`deploy/VULTR_CHECKLIST.md`](deploy/VULTR_CHECKLIST.md), `docker-compose.yml`.

Timestamps are **TIMESTAMP WITHOUT TIME ZONE** (naive BattLeDIM clock). Do not attach a geographic timezone.

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
- Leak ground-truth files are not downloaded or processed in this milestone.
