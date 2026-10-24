#!/usr/bin/env python3
"""January-only raw vs readings_15m CAGG benchmark.

Single reused connection, 7× alternating arms, count-weighted aggregates.
Windows stay inside January 2019 coverage. No import/upgrade/delete.
Does not print DATABASE_URL or other secrets.
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.config import get_settings  # noqa: E402
from app.db import get_connection  # noqa: E402

REPEATS = 7
JAN_START = datetime(2019, 1, 1, 0, 0, 0)
JAN_END_EXCL = datetime(2019, 2, 1, 0, 0, 0)
ARTIFACT_PATH = REPO_ROOT / "artifacts" / "january_raw_cagg_benchmark.json"

# rippple CAGG columns: count, sum, min, max
SQL_Q1_RAW = """
SELECT time_bucket(INTERVAL '15 minutes', ts) AS bucket,
       sensor_id,
       COUNT(*)::BIGINT AS sample_count,
       SUM(value) AS value_sum,
       MIN(value) AS value_min,
       MAX(value) AS value_max
FROM readings
WHERE ts >= %s AND ts < %s
  AND sensor_id = ANY(%s)
GROUP BY 1, 2
ORDER BY 1, 2
"""

SQL_Q1_CAGG = """
SELECT bucket,
       sensor_id,
       count::BIGINT AS sample_count,
       sum AS value_sum,
       min AS value_min,
       max AS value_max
FROM readings_15m
WHERE bucket >= %s AND bucket < %s
  AND sensor_id = ANY(%s)
ORDER BY 1, 2
"""

SQL_Q2_RAW = """
SELECT time_bucket(INTERVAL '1 hour', ts) AS bucket,
       sensor_id,
       COUNT(*)::BIGINT AS sample_count,
       SUM(value) AS value_sum,
       MIN(value) AS value_min,
       MAX(value) AS value_max
FROM readings
WHERE ts >= %s AND ts < %s
  AND sensor_id = ANY(%s)
GROUP BY 1, 2
ORDER BY 1, 2
"""

SQL_Q2_CAGG = """
SELECT time_bucket(INTERVAL '1 hour', bucket) AS bucket,
       sensor_id,
       SUM(count)::BIGINT AS sample_count,
       SUM(sum) AS value_sum,
       MIN(min) AS value_min,
       MAX(max) AS value_max
FROM readings_15m
WHERE bucket >= %s AND bucket < %s
  AND sensor_id = ANY(%s)
GROUP BY 1, 2
ORDER BY 1, 2
"""

SQL_Q3_RAW = """
SELECT time_bucket(INTERVAL '1 day', ts) AS bucket,
       sensor_id,
       COUNT(*)::BIGINT AS sample_count,
       SUM(value) AS value_sum,
       MIN(value) AS value_min,
       MAX(value) AS value_max
FROM readings
WHERE ts >= %s AND ts < %s
  AND sensor_id = ANY(%s)
GROUP BY 1, 2
ORDER BY 1, 2
"""

SQL_Q3_CAGG = """
SELECT time_bucket(INTERVAL '1 day', bucket) AS bucket,
       sensor_id,
       SUM(count)::BIGINT AS sample_count,
       SUM(sum) AS value_sum,
       MIN(min) AS value_min,
       MAX(max) AS value_max
FROM readings_15m
WHERE bucket >= %s AND bucket < %s
  AND sensor_id = ANY(%s)
GROUP BY 1, 2
ORDER BY 1, 2
"""

WORKLOADS = [
    {
        "id": "q1_24h_15m",
        "label": "24h × 15m pressure",
        "supports": "Demo scrubbing / episode context at native CAGG grain",
        "raw_sql": SQL_Q1_RAW,
        "cagg_sql": SQL_Q1_CAGG,
    },
    {
        "id": "q2_january_hourly",
        "label": "January × hourly pressure",
        "supports": "Multi-week investigation context (January-only coverage)",
        "raw_sql": SQL_Q2_RAW,
        "cagg_sql": SQL_Q2_CAGG,
    },
    {
        "id": "q3_january_daily",
        "label": "January × daily by sensor",
        "supports": "Coverage / baseline overview across stored January history",
        "raw_sql": SQL_Q3_RAW,
        "cagg_sql": SQL_Q3_CAGG,
    },
]


def _percentile(sorted_samples: list[float], p: float) -> float:
    if not sorted_samples:
        return float("nan")
    if len(sorted_samples) == 1:
        return float(sorted_samples[0])
    k = (len(sorted_samples) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_samples) - 1)
    if f == c:
        return float(sorted_samples[f])
    return float(sorted_samples[f] + (sorted_samples[c] - sorted_samples[f]) * (k - f))


def _fmt(ts: datetime) -> str:
    return ts.strftime("%Y-%m-%d %H:%M:%S")


def _pressure_ids(cur) -> list[str]:
    cur.execute(
        """
        SELECT id FROM sensors
        WHERE measurement_type = 'pressure'
        ORDER BY id
        """
    )
    return [r["id"] for r in cur.fetchall()]


def _january_windows(cur) -> dict[str, tuple[datetime, datetime]]:
    cur.execute(
        """
        SELECT MIN(ts) AS tmin, MAX(ts) AS tmax FROM readings
        WHERE ts >= %s AND ts < %s
        """,
        (JAN_START, JAN_END_EXCL),
    )
    raw = cur.fetchone()
    cur.execute(
        """
        SELECT MIN(bucket) AS bmin, MAX(bucket) AS bmax FROM readings_15m
        WHERE bucket >= %s AND bucket < %s
        """,
        (JAN_START, JAN_END_EXCL),
    )
    cagg = cur.fetchone()
    if not raw["tmin"] or not cagg["bmin"]:
        raise RuntimeError("No January readings/CAGG coverage for benchmark")

    start = max(raw["tmin"], cagg["bmin"], JAN_START)
    end_excl = min(
        raw["tmax"] + timedelta(minutes=5),
        cagg["bmax"] + timedelta(minutes=15),
        JAN_END_EXCL,
    )

    # Q1: last 24h inside January coverage
    q1_e = end_excl
    q1_s = q1_e - timedelta(hours=24)
    if q1_s < start:
        q1_s = start
    q1_s = q1_s.replace(minute=(q1_s.minute // 15) * 15, second=0, microsecond=0)

    # Q2/Q3: full January intersection
    day_start = datetime(start.year, start.month, start.day)
    if day_start < start:
        day_start = day_start + timedelta(days=1)
    day_end = datetime(end_excl.year, end_excl.month, end_excl.day)
    if day_end > end_excl:
        day_end = datetime(end_excl.year, end_excl.month, end_excl.day)

    return {
        "q1_24h_15m": (q1_s, q1_e),
        "q2_january_hourly": (day_start, day_end if day_end > day_start else end_excl),
        "q3_january_daily": (day_start, day_end if day_end > day_start else end_excl),
        "_coverage": (start, end_excl),
    }


def _fetch(cur, sql: str, params: tuple) -> list[dict[str, Any]]:
    cur.execute(sql, params)
    return list(cur.fetchall())


def _compare(raw_rows: list[dict], cagg_rows: list[dict]) -> dict[str, Any]:
    raw_map = {(r["bucket"], r["sensor_id"]): r for r in raw_rows}
    cagg_map = {(r["bucket"], r["sensor_id"]): r for r in cagg_rows}
    missing_cagg = [k for k in raw_map if k not in cagg_map]
    missing_raw = [k for k in cagg_map if k not in raw_map]
    matched = 0
    for k, rr in raw_map.items():
        cr = cagg_map.get(k)
        if cr is None:
            continue
        ok = (
            int(rr["sample_count"]) == int(cr["sample_count"])
            and abs(float(rr["value_sum"]) - float(cr["value_sum"])) < 1e-6
            and abs(float(rr["value_min"]) - float(cr["value_min"])) < 1e-9
            and abs(float(rr["value_max"]) - float(cr["value_max"])) < 1e-9
        )
        if ok:
            matched += 1
    return {
        "raw_row_count": len(raw_rows),
        "cagg_row_count": len(cagg_rows),
        "matched_rows": matched,
        "missing_in_cagg": len(missing_cagg),
        "missing_in_raw": len(missing_raw),
        "outputs_match": (
            not missing_cagg
            and not missing_raw
            and matched == len(raw_rows)
            and len(raw_rows) == len(cagg_rows)
        ),
        "average_method": "SUM(value_sum)/SUM(sample_count) — never avg-of-avgs",
    }


def _explain_exec_s(cur, sql: str, params: tuple) -> float:
    cur.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + sql, params)
    plan_row = cur.fetchone()
    plan = plan_row[list(plan_row.keys())[0]]
    if isinstance(plan, str):
        plan = json.loads(plan)
    root = plan[0] if isinstance(plan, list) else plan
    return float(root["Execution Time"]) / 1000.0


def _summarize(samples: list[float]) -> dict[str, float]:
    ordered = sorted(samples)
    return {
        "median_s": float(statistics.median(samples)),
        "p95_s": _percentile(ordered, 95.0),
        "mean_s": float(statistics.fmean(samples)),
        "min_s": float(min(samples)),
        "max_s": float(max(samples)),
    }


def main() -> int:
    get_settings.cache_clear()
    if not get_settings().database_url:
        print("FAIL: DATABASE_URL not configured")
        return 1

    run_started = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    coverage_meta: dict[str, Any] = {}
    results: list[dict[str, Any]] = []

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SET statement_timeout = '120s'")
            pressures = _pressure_ids(cur)
            windows = _january_windows(cur)
            cov_s, cov_e = windows["_coverage"]
            cur.execute(
                """
                SELECT COUNT(*)::BIGINT AS n FROM readings
                WHERE ts >= %s AND ts < %s
                """,
                (JAN_START, JAN_END_EXCL),
            )
            jan_readings = int(cur.fetchone()["n"])
            cur.execute(
                """
                SELECT COUNT(*)::BIGINT AS n FROM readings_15m
                WHERE bucket >= %s AND bucket < %s
                """,
                (JAN_START, JAN_END_EXCL),
            )
            jan_cagg = int(cur.fetchone()["n"])
            coverage_meta = {
                "scope": "january_2019_only",
                "readings_n": jan_readings,
                "readings_tmin": _fmt(cov_s),
                "readings_tmax": _fmt(cov_e - timedelta(minutes=5)),
                "cagg_n": jan_cagg,
                "pressure_sensor_count": len(pressures),
            }

            print("=== January-only raw vs CAGG benchmark ===")
            print(f"coverage: [{_fmt(cov_s)}, {_fmt(cov_e)})")
            print(f"pressure_sensors: {len(pressures)}")
            print(f"method: {REPEATS}× alternating raw/CAGG, same connection")
            print(f"timing: DB=EXPLAIN ANALYZE Execution Time; client=execute+fetchall")
            print()

            for wl in WORKLOADS:
                start, end = windows[wl["id"]]
                if start >= end:
                    print(f"{wl['id']}: SKIPPED (empty window)")
                    continue
                params = (start, end, pressures)

                raw_rows = _fetch(cur, wl["raw_sql"], params)
                cagg_rows = _fetch(cur, wl["cagg_sql"], params)
                equivalence = _compare(raw_rows, cagg_rows)

                # Warm once, then alternate (order flips each repeat).
                _fetch(cur, wl["raw_sql"], params)
                _fetch(cur, wl["cagg_sql"], params)

                db_raw: list[float] = []
                db_cagg: list[float] = []
                client_raw: list[float] = []
                client_cagg: list[float] = []

                for i in range(REPEATS):
                    if i % 2 == 0:
                        t0 = time.perf_counter()
                        _fetch(cur, wl["raw_sql"], params)
                        client_raw.append(time.perf_counter() - t0)
                        t0 = time.perf_counter()
                        _fetch(cur, wl["cagg_sql"], params)
                        client_cagg.append(time.perf_counter() - t0)
                    else:
                        t0 = time.perf_counter()
                        _fetch(cur, wl["cagg_sql"], params)
                        client_cagg.append(time.perf_counter() - t0)
                        t0 = time.perf_counter()
                        _fetch(cur, wl["raw_sql"], params)
                        client_raw.append(time.perf_counter() - t0)

                for i in range(REPEATS):
                    if i % 2 == 0:
                        db_raw.append(_explain_exec_s(cur, wl["raw_sql"], params))
                        db_cagg.append(_explain_exec_s(cur, wl["cagg_sql"], params))
                    else:
                        db_cagg.append(_explain_exec_s(cur, wl["cagg_sql"], params))
                        db_raw.append(_explain_exec_s(cur, wl["raw_sql"], params))

                raw_db = _summarize(db_raw)
                cagg_db = _summarize(db_cagg)
                raw_client = _summarize(client_raw)
                cagg_client = _summarize(client_cagg)
                speedup = (
                    raw_db["median_s"] / cagg_db["median_s"]
                    if cagg_db["median_s"] > 0
                    else float("inf")
                )

                row = {
                    "id": wl["id"],
                    "label": wl["label"],
                    "supports": wl["supports"],
                    "supports_investigation": wl["supports"],
                    "window": {"start": _fmt(start), "end_exclusive": _fmt(end)},
                    "equivalence": equivalence,
                    "database_execution_explain": {
                        "scope": "database_execution",
                        "note": (
                            "EXPLAIN (ANALYZE, BUFFERS) Execution Time only — "
                            "not application or browser loading time."
                        ),
                        "raw": raw_db,
                        "cagg": cagg_db,
                    },
                    "client_roundtrip": {
                        "scope": "psycopg_execute_fetchall",
                        "raw": raw_client,
                        "cagg": cagg_client,
                    },
                    "raw_db": raw_db,
                    "cagg_db": cagg_db,
                    "raw_client": raw_client,
                    "cagg_client": cagg_client,
                    "db_median_speedup": speedup,
                    "speedup_note": (
                        f"CAGG database execution median is {speedup:.2f}× faster than raw."
                        if speedup >= 1.05
                        else f"CAGG ≈ raw (median ratio {speedup:.2f}×)."
                    ),
                }
                results.append(row)

                match = "yes" if equivalence["outputs_match"] else "NO"
                print(f"### {wl['label']}")
                print(f"supports: {wl['supports']}")
                print(f"window: [{_fmt(start)}, {_fmt(end)})")
                print(
                    f"match: {match} "
                    f"(rows raw={equivalence['raw_row_count']} "
                    f"cagg={equivalence['cagg_row_count']})"
                )
                print(
                    f"DB median: raw {raw_db['median_s']*1000:.2f} ms → "
                    f"CAGG {cagg_db['median_s']*1000:.2f} ms "
                    f"(speedup {speedup:.2f}×)"
                )
                print(
                    f"Client median: raw {raw_client['median_s']*1000:.2f} ms → "
                    f"CAGG {cagg_client['median_s']*1000:.2f} ms"
                )
                print()

    print("=== summary ===")
    print(
        f"{'Workload':<28} {'Match':<6} {'Raw DB':>10} {'CAGG DB':>10} {'Speedup':>8}"
    )
    for r in results:
        print(
            f"{r['label']:<28} "
            f"{'yes' if r['equivalence']['outputs_match'] else 'NO':<6} "
            f"{r['raw_db']['median_s']*1000:8.2f}ms "
            f"{r['cagg_db']['median_s']*1000:8.2f}ms "
            f"{r['db_median_speedup']:7.2f}×"
        )

    artifact = {
        "schema_version": 1,
        "title": "January-only raw versus readings_15m CAGG benchmark",
        "run_date_utc": run_started[:10],
        "run_started_utc": run_started,
        "repeats": REPEATS,
        "method": (
            "Single reused connection; arms alternate raw/CAGG each repeat; "
            "database timings from EXPLAIN (ANALYZE, BUFFERS) Execution Time."
        ),
        "timing_label": "database_execution",
        "not_application_loading_time": True,
        "compression_enabled": False,
        "coverage": coverage_meta,
        "workloads": results,
    }
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_PATH.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    print(f"wrote artifact: {ARTIFACT_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
