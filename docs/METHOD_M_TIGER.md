# Method M evidence in Tiger Data

Optional database-backed store for the **frozen** January 2019 five-minute
Experimental Method M serving artifact. Detector outputs are persisted exactly;
there is no retraining and no new hydraulic computation.

## Default remains file-backed

| Setting | Behavior |
| --- | --- |
| `RIPPLE_METHOD_M_STORE=file` (default) | `artifacts/method_m_experimental_january/` — rollback path |
| `RIPPLE_METHOD_M_STORE=tiger` | Same API contract from `method_m_*` tables |
| `RIPPLE_METHOD_M_RUN_ID` | Required if more than one run is present; prevents silent mixing |

Do **not** enable `tiger` in production until migration + import + parity tests
pass locally.

## Schema (migration `003_method_m_evidence.sql`)

1. `method_m_runs` — relational run metadata + provenance hashes  
2. `method_m_scores` — hypertable of network scores (5-minute stamps)  
3. `method_m_sensor_evidence` — hypertable of per-sensor contributors  
4. `method_m_notifications` — relational notify/end/peak records  

Evaluation labels and raw SCADA are **not** imported here. Pressure context
continues to come from existing `readings` / `readings_15m` queries.

## Storage projection (January freeze)

| Item | Size |
| --- | --- |
| File artifact `serving_hours.json` | ~8.8 MiB |
| Manifest projected derived tables | ~60.7 MiB |
| Importer working estimate (with index cushion) | 65 MiB |
| Observed `pg_database_size` delta after local import | ~13.9 MiB |
| Service limit / working ceiling | 750 MiB / 600 MiB |

Importer refuses if `pg_database_size + 65 MiB` would exceed the 80% ceiling.
Observed growth was well under that conservative estimate (8928 scores +
41107 contributor rows + 2 notifications).

## Local migration + import

```bash
# From repo root; uses project-root .env DATABASE_URL + RIPPLE_STORAGE_LIMIT_BYTES
python scripts/migrate.py
python scripts/import_method_m_january.py --dry-run
python scripts/import_method_m_january.py
# Second run must report idempotent_skip
python scripts/import_method_m_january.py

# Optional: exercise Tiger presenter locally (file remains default)
export RIPPLE_METHOD_M_STORE=tiger
pytest backend/tests/test_method_m_tiger_parity.py -q
```

## Score timeline API

`GET /api/experimental/method-m-timeline?at=` returns the preceding 24 hours of
frozen `method_m_scores` (and in-window notify markers) for the selected run,
ending at `floor(cursor)` on the five-minute grid. Requires
`RIPPLE_METHOD_M_STORE=tiger` — there is no file-artifact fallback.
Aligned pressure uses existing `/api/sensors/{id}/readings` on the same window;
30-day hourly CAGG history remains on `/api/sensors/{id}/hourly-history`.

## Useful SQL workflow

For an active warning stamp, join contributors to sensor metadata; use existing
raw-reading APIs for pressure:

```sql
SELECT e.sensor_id, e.abs_z_calibrated, e.delta_m3h,
       s.measurement_type, s.unit, s.network_element_id
FROM method_m_sensor_evidence e
LEFT JOIN sensors s ON s.id = e.sensor_id
WHERE e.run_id = 'method_m_5min_jan2019'
  AND e.ts = TIMESTAMP '2019-01-15 23:00:00'
ORDER BY e.abs_z_calibrated DESC;
```

Python helper: `app.method_m_db.fetch_contributors_with_sensor_meta`.

## Query timing

Local application wall-clock for one Method M present at the 15 Jan notify
(not database `EXPLAIN ANALYZE`, not a sponsor speedup claim):

| Store | Wall clock (approx.) |
| --- | --- |
| File | ~0.08 s |
| Tiger | ~0.25 s |

Tiger is slightly slower here for a single cursor present (multiple SQL
round-trips vs an in-memory artifact). The value of the Tiger path is
persistence, SQL joins to sensor metadata / raw readings, and shared storage
with the rest of the investigation DB — not a claimed present-call speedup.

Live Tiger evidence panel timings for raw-vs-CAGG still come from the saved
January benchmark artifact (not re-run on page load).

## Rollback

Unset or set `RIPPLE_METHOD_M_STORE=file`. Leave tables in place; they are unused
when the file store is selected.
